"""Shared email/SMS helpers used across auth flows and library workflows."""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail, EmailMultiAlternatives
from django.utils import timezone

def send_email_code(to_email, code, purpose='login'):
    label = {
        'login': 'login',
        'registration': 'account verification',
    }.get(purpose, purpose)
    send_mail(
        subject=f'Your GCTU Library {label} code',
        message=f'Your verification code is {code}. It expires in {settings.OTP_VALIDITY_MINUTES} minutes.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )

def send_phone_code(phone_number, code):
    import re
    import requests

    if not phone_number:
        raise ValueError('No phone number on file for this account.')

    phone = re.sub(r'\D', '', str(phone_number))
    if phone.startswith('0') and len(phone) == 10:
        phone = '233' + phone[1:]
    elif len(phone) == 9:
        phone = '233' + phone

    response = requests.post(
        settings.ARKESEL_API_URL,
        headers={'api-key': settings.ARKESEL_API_KEY},
        json={
            'sender': settings.ARKESEL_SENDER_ID,
            'message': f'Your GCTU Library verification code is {code}.',
            'recipients': [phone],
        },
        timeout=10,
    )
    response.raise_for_status()
    return response

def _staff_emails():
    return list(
        User.objects.filter(is_staff=True, is_active=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )

def notify_admins(subject, message, html_message=None):
    """Email every active staff user. Never blocks the student action."""
    admin_emails = _staff_emails()
    if not admin_emails:
        return
    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=admin_emails,
        )
        if html_message:
            email.attach_alternative(html_message, 'text/html')
        email.send(fail_silently=True)
    except Exception:
        pass

def notify_borrow_request(user, book):
    """Formal email when a student requests to borrow a book."""
    now = timezone.now().strftime('%d %B %Y, %I:%M %p')
    student_name = user.get_full_name() or user.username
    student_email = user.email or 'Not provided'

    subject = f'[GCTU Library] Borrow Request – {book.title}'

    text_message = f"""\
Ghana Communication Technology University Library
------------------------------------------------

Dear Librarian,

A new book borrow request has been submitted and requires your review.

Request Details
---------------
Student Index Number : {user.username}
Student Name         : {student_name}
Student Email        : {student_email}
Book Title           : {book.title}
Author               : {book.author}
Request Date         : {now}
Status               : Pending Approval

Please log in to the Librarian Dashboard to approve or reject this request.

GCTU Smart Library System
This is an automated notification. Please do not reply to this email.
"""

    html_message = f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #222; line-height: 1.5;">
  <div style="max-width: 640px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
    <div style="background: #0d6efd; color: #fff; padding: 16px 20px;">
      <h2 style="margin: 0; font-size: 18px;">GCTU Library – Borrow Request</h2>
    </div>
    <div style="padding: 20px;">
      <p>Dear Librarian,</p>
      <p>A new book borrow request has been submitted and requires your review.</p>

      <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Student Index Number</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{user.username}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Student Name</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{student_name}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Student Email</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{student_email}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Book Title</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{book.title}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Author</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{book.author}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Request Date</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{now}</td></tr>
        <tr><td style="padding: 8px;"><strong>Status</strong></td>
            <td style="padding: 8px;">Pending Approval</td></tr>
      </table>

      <p>Please log in to the <strong>Librarian Dashboard</strong> to approve or reject this request.</p>
      <p style="color: #666; font-size: 12px; margin-top: 24px;">
        GCTU Smart Library System<br>
        This is an automated notification. Please do not reply to this email.
      </p>
    </div>
  </div>
</body>
</html>
"""
    notify_admins(subject, text_message, html_message)

def notify_return_request(user, book):
    """Formal email when a student requests to return a book."""
    now = timezone.now().strftime('%d %B %Y, %I:%M %p')
    student_name = user.get_full_name() or user.username
    student_email = user.email or 'Not provided'

    subject = f'[GCTU Library] Return Request – {book.title}'

    text_message = f"""\
Ghana Communication Technology University Library
------------------------------------------------

Dear Librarian,

A book return request has been submitted and requires your review.

Request Details
---------------
Student Index Number : {user.username}
Student Name         : {student_name}
Student Email        : {student_email}
Book Title           : {book.title}
Author               : {book.author}
Request Date         : {now}
Status               : Return Pending Approval

Please log in to the Librarian Dashboard to confirm this return.

GCTU Smart Library System
This is an automated notification. Please do not reply to this email.
"""

    html_message = f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #222; line-height: 1.5;">
  <div style="max-width: 640px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
    <div style="background: #198754; color: #fff; padding: 16px 20px;">
      <h2 style="margin: 0; font-size: 18px;">GCTU Library – Return Request</h2>
    </div>
    <div style="padding: 20px;">
      <p>Dear Librarian,</p>
      <p>A book return request has been submitted and requires your review.</p>

      <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Student Index Number</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{user.username}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Student Name</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{student_name}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Student Email</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{student_email}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Book Title</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{book.title}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Author</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{book.author}</td></tr>
        <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Request Date</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{now}</td></tr>
        <tr><td style="padding: 8px;"><strong>Status</strong></td>
            <td style="padding: 8px;">Return Pending Approval</td></tr>
      </table>

      <p>Please log in to the <strong>Librarian Dashboard</strong> to confirm this return.</p>
      <p style="color: #666; font-size: 12px; margin-top: 24px;">
        GCTU Smart Library System<br>
        This is an automated notification. Please do not reply to this email.
      </p>
    </div>
  </div>
</body>
</html>
"""
    notify_admins(subject, text_message, html_message)