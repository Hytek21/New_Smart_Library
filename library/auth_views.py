import random

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from .models import OTPVerification
from .notifications import send_email_code
from django import forms
from django.contrib.auth import authenticate




class IndexNumberAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Index Number'
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'e.g. 42XXXXXXXX',
            'autofocus': True,
        })
        self.fields['password'].widget.attrs.update({'class': 'form-control'})

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            from django.contrib.auth.models import User

            # Check if the index number exists
            if not User.objects.filter(username=username).exists():
                raise forms.ValidationError(
                    "Index number does not exist in the system.",
                    code='invalid_login',
                )

            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
            )

            if self.user_cache is None:
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class AdminAuthenticationForm(AuthenticationForm):
    """Plain username/password form for staff. Kept for direct/bookmarked
    access to /admin-login/, though the main login page now handles staff
    accounts automatically without needing this separate page.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'autofocus': True})
        self.fields['password'].widget.attrs.update({'class': 'form-control'})

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise self.get_invalid_login_error()


# ---------------------------------------------------------------------------
# OTP helpers
# ---------------------------------------------------------------------------

def generate_otp_code():
    return f"{random.randint(0, 999999):06d}"


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class StudentLoginView(LoginView):
    """The one and only login page. Username/password first; what happens
    next depends on the account:
      - everyone else goes through the email step (verify_otp)
    """
    template_name = 'registration/login.html'
    authentication_form = IndexNumberAuthenticationForm
    redirect_authenticated_user = False

    def form_valid(self, form):
        user = form.get_user()


        self.request.session['pre_2fa_user_id'] = user.pk
        self.request.session['pre_2fa_user_email'] = user.email
        self.request.session['pre_2fa_is_staff'] = user.is_staff
        return redirect('verify_otp')


class AdminLoginView(LoginView):
    """Kept for direct/bookmarked access — not linked from the main login
    page anymore, since StudentLoginView now handles staff accounts too.
    """
    template_name = 'registration/admin_login.html'
    authentication_form = AdminAuthenticationForm

    def get_success_url(self):
        return '/librarian/'


def verify_otp(request):
    user_id = request.session.get('pre_2fa_user_id')
    if not user_id:
        messages.error(request, 'Please log in again.')
        return redirect('login')

    from django.contrib.auth.models import User
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        request.session.pop('pre_2fa_user_id', None)
        return redirect('login')

    otp_sent = request.session.get('otp_channel')

    # Auto-send email OTP the first time the user lands on this page
    if request.method == 'GET' and not otp_sent:
        code = generate_otp_code()
        try:
            send_email_code(user.email, code, purpose='login')
            OTPVerification.objects.create(user=user, code=code, channel='email')
            request.session['otp_channel'] = 'email'
            otp_sent = 'email'
            messages.success(request, f'A verification code was sent to {user.email}.')
        except Exception as e:
            messages.error(request, f"Couldn't send the email code: {e}")

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'send':
            # Only email is allowed at login
            code = generate_otp_code()
            try:
                send_email_code(user.email, code, purpose='login')
                OTPVerification.objects.create(user=user, code=code, channel='email')
                request.session['otp_channel'] = 'email'
                messages.success(request, f'A verification code was sent to {user.email}.')
            except Exception as e:
                messages.error(request, f"Couldn't send the code: {e}")
            return render(request, 'registration/verify_otp.html', {
                'otp_sent': 'email',
                'user_email': user.email,
            })

        if action == 'verify':
            code = request.POST.get('code', '').strip()
            otp = OTPVerification.objects.filter(
                user=user, channel='email', is_used=False
            ).order_by('-created_at').first()

            if otp and not otp.is_expired() and otp.code == code:
                otp.is_used = True
                otp.save()

                is_staff = request.session.pop('pre_2fa_is_staff', False)
                request.session.pop('pre_2fa_user_id', None)
                request.session.pop('otp_channel', None)
                request.session.pop('pre_2fa_user_email', None)
                auth_login(request, user)

                if is_staff:
                    return redirect('librarian_dashboard')
                return redirect(settings.LOGIN_REDIRECT_URL)

            messages.error(request, 'That code is incorrect or has expired.')
            return render(request, 'registration/verify_otp.html', {
                'otp_sent': 'email',
                'user_email': user.email,
            })

    return render(request, 'registration/verify_otp.html', {
        'otp_sent': otp_sent,
        'user_email': user.email,
    })
