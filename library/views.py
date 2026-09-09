import re
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from .models import UserProfile
from .forms import RegisterForm
from django.views.generic import ListView
from django.db.models import Q
from nltk import word_tokenize
from nltk.stem import PorterStemmer
from .models import Book
from .models import Borrowing
from django.views.generic import DetailView
from django.contrib.auth.views import LoginView
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from .models import Book, Borrowing
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import CreateView
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.contrib.messages.views import SuccessMessageMixin
import joblib
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from difflib import SequenceMatcher

from .auth_views import generate_otp_code
from .notifications import send_email_code, send_phone_code, notify_admins, notify_borrow_request, notify_return_request
from .models import FACULTY_CHOICES
from django.contrib.auth.hashers import make_password

from .validators import is_email_valid


def _code_expired(sent_at_iso):
    if not sent_at_iso:
        return True
    sent_at = timezone.datetime.fromisoformat(sent_at_iso)
    if timezone.is_naive(sent_at):
        sent_at = timezone.make_aware(sent_at)
    from django.conf import settings
    return timezone.now() > sent_at + timedelta(minutes=settings.OTP_VALIDITY_MINUTES)


def register(request):
    values = {'username': '', 'email': '', 'phone_number': '', 'faculty': ''}

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone_number', '').strip()
        faculty = request.POST.get('faculty', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')


        values = {'username': username, 'email': email, 'phone_number': phone, 'faculty': faculty}

        def error(msg):
            return render(request, 'registration/register.html', {'error': msg, 'values': values})

        if not username.isdigit() or not (6 <= len(username) <= 12):
            return error('Index number should be 6-12 digits (e.g. 42XXXXXXXX)')

        if faculty not in dict(FACULTY_CHOICES):
            return error('Please select your faculty')

        if not email:
            return error('Email is required')

        if not phone:
            return error('Phone number is required')

        if password1 != password2:
            return error('Passwords do not match')

        if User.objects.filter(username=username).exists():
            return error('An account with this index number already exists')

        if User.objects.filter(email__iexact=email).exists():
            return error('An account with this email already exists')

        if UserProfile.objects.filter(phone_number=phone).exists():
            return error('An account with this phone number already exists')

        try:
            validate_password(password1)
        except ValidationError as e:
            return error(' '.join(e.messages))

        ok, reason = is_email_valid(email)
        if not ok:
            return error(reason)

        # Don't create the account yet — stash everything (password already
        # hashed) in the session and require both email + phone verification
        # first. See verify_registration below.
        email_code = generate_otp_code()
        phone_code = generate_otp_code()

        try:
            send_email_code(email, email_code, purpose='registration')
        except Exception as e:
            return error(f"Couldn't send the email verification code: {e}")

        try:
            send_phone_code(phone, phone_code)
        except Exception as e:
            return error(f"Couldn't send the phone verification code: {e}")

        request.session['pending_registration'] = {
            'username': username,
            'email': email,
            'phone': phone,
            'faculty': faculty,
            'password_hash': make_password(password1),
            'email_code': email_code,
            'phone_code': phone_code,
            'email_verified': False,
            'phone_verified': False,
            'email_sent_at': timezone.now().isoformat(),
            'phone_sent_at': timezone.now().isoformat(),
        }
        return redirect('verify_registration')

    return render(request, 'registration/register.html', {'values': values})


def verify_registration(request):
    pending = request.session.get('pending_registration')
    if not pending:
        messages.error(request, 'Please start registration again.')
        return redirect('register')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'verify_email':
            code = request.POST.get('code', '').strip()
            if _code_expired(pending.get('email_sent_at')):
                messages.error(request, 'That email code expired. Resend a new one.')
            elif code == pending.get('email_code'):
                pending['email_verified'] = True
                messages.success(request, 'Email verified.')
            else:
                messages.error(request, 'Incorrect email code.')

        elif action == 'verify_phone':
            code = request.POST.get('code', '').strip()
            if _code_expired(pending.get('phone_sent_at')):
                messages.error(request, 'That phone code expired. Resend a new one.')
            elif code == pending.get('phone_code'):
                pending['phone_verified'] = True
                messages.success(request, 'Phone verified.')
            else:
                messages.error(request, 'Incorrect phone code.')

        elif action == 'resend_email':
            new_code = generate_otp_code()
            try:
                send_email_code(pending['email'], new_code, purpose='registration')
                pending['email_code'] = new_code
                pending['email_sent_at'] = timezone.now().isoformat()
                messages.success(request, 'A new email code was sent.')
            except Exception as e:
                messages.error(request, f"Couldn't resend the email code: {e}")

        elif action == 'resend_phone':
            new_code = generate_otp_code()
            try:
                send_phone_code(pending['phone'], new_code)
                pending['phone_code'] = new_code
                pending['phone_sent_at'] = timezone.now().isoformat()
                messages.success(request, 'A new phone code was sent.')
            except Exception as e:
                messages.error(request, f"Couldn't resend the phone code: {e}")

        request.session['pending_registration'] = pending
        request.session.modified = True

        if pending['email_verified'] and pending['phone_verified']:
            if User.objects.filter(username=pending['username']).exists():
                messages.error(request, 'That index number was just registered by someone else.')
                del request.session['pending_registration']
                return redirect('register')
            if User.objects.filter(email__iexact=pending['email']).exists():
                messages.error(request, 'That email was just registered by someone else.')
                del request.session['pending_registration']
                return redirect('register')
            if UserProfile.objects.filter(phone_number=pending['phone']).exists():
                messages.error(request, 'That phone number was just registered by someone else.')
                del request.session['pending_registration']
                return redirect('register')

            user = User(username=pending['username'], email=pending['email'])
            user.password = pending['password_hash']  # already hashed via make_password
            user.save()
            UserProfile.objects.create(
                user=user,
                phone_number=pending['phone'],
                faculty=pending['faculty'],
            )
            del request.session['pending_registration']
            login(request, user)
            messages.success(request, 'Account created — welcome!')
            return redirect('home')

    return render(request, 'registration/verify_registration.html', {
        'email': pending['email'],
        'phone': pending['phone'],
        'email_verified': pending['email_verified'],
        'phone_verified': pending['phone_verified'],
    })


# Simple synonym dictionary for academic/library terms
SYNONYMS = {
    "ai": ["artificial intelligence", "machine learning", "ml", "deep learning"],
    "intelligent": ["intelligence", "smart", "cognitive"],
    "intelligence": ["intelligent", "smart", "ai"],
    "program": ["programming", "coding", "code", "software"],
    "programming": ["program", "coding", "code", "software development"],
    "code": ["coding", "programming", "program"],
    "data": ["dataset", "information", "database"],
    "database": ["data", "db", "sql"],
    "network": ["networking", "computer network"],
    "security": ["cybersecurity", "information security"],
    "web": ["website", "web development", "frontend", "backend"],
    "algorithm": ["algorithms", "computation"],
    "science": ["scientific"],
    "math": ["mathematics", "mathematical"],
    "history": ["historical"],
    "economy": ["economics", "economic"],
    "business": ["management", "commerce"],
}

def expand_query_with_synonyms(query):
    query = query.lower().strip()
    words = query.split()
    expanded_terms = set(words)

    for word in words:
        if word in SYNONYMS:
            expanded_terms.update(SYNONYMS[word])


    expanded_query = " ".join(expanded_terms)
    return query, expanded_query


@login_required
def borrow_book(request, pk):
    book = get_object_or_404(Book, pk=pk)

    if book.available <= 0:
        messages.error(request, '❌ This book is currently not available.')
        return redirect('book_detail', pk=pk)

    # Create pending request
    Borrowing.objects.create(
        user=request.user,
        book=book,
        due_date=timezone.now() + timedelta(days=14),
        status='pending'
    )

    notify_borrow_request(request.user, book)

    messages.success(request,f'✅ Borrow request for "{book.title}" has been submitted. Waiting for librarian approval.')
    return redirect('my_library')


class MyLibraryView(LoginRequiredMixin, ListView):
    model = Borrowing
    template_name = 'library/my_library.html'
    context_object_name = 'borrowings'

    def get_queryset(self):
        return Borrowing.objects.filter(
            user=self.request.user,
            return_date__isnull=True
        ).order_by('due_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        borrowings = context['borrowings']

        context['pending_borrowings'] = borrowings.filter(status='pending')
        context['active_borrowings'] = borrowings.filter(status='approved')
        context['returned_pending'] = borrowings.filter(status='returned_pending')
        context['rejected_borrowings'] = borrowings.filter(status='rejected')

        # Full history (including returned books) for the borrowing chart,
        # grouped by month over the last 6 months.
        import json

        all_history = Borrowing.objects.filter(user=self.request.user)
        today = timezone.now().replace(day=1)

        # Build the last 6 month buckets (oldest to newest)
        cursor = today
        buckets = []
        for _ in range(6):
            buckets.append(cursor)
            prev_month = cursor.month - 1 or 12
            prev_year = cursor.year - 1 if cursor.month == 1 else cursor.year
            cursor = cursor.replace(year=prev_year, month=prev_month)
        buckets.reverse()

        counts = []
        labels = []
        for bucket_start in buckets:
            next_month = bucket_start.month + 1 if bucket_start.month < 12 else 1
            next_year = bucket_start.year + 1 if bucket_start.month == 12 else bucket_start.year
            bucket_end = bucket_start.replace(year=next_year, month=next_month)
            labels.append(bucket_start.strftime('%b %Y'))
            counts.append(
                all_history.filter(
                    borrow_date__gte=bucket_start, borrow_date__lt=bucket_end
                ).count()
            )

        context['borrowing_chart_labels'] = json.dumps(labels)
        context['borrowing_chart_counts'] = json.dumps(counts)

        return context


class BookDetailView(DetailView):
    model = Book
    template_name = 'library/book_detail.html'
    context_object_name = 'book'

class HomeView(TemplateView):
    template_name = 'library/home.html'

class RegisterView(SuccessMessageMixin, CreateView):
    form_class = UserCreationForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('login')
    success_message = "Account created."


stemmer = PorterStemmer()

def clean_and_stem(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r'[^a-zA-Z\s]', ' ', text)
    tokens = word_tokenize(text)
    stemmed = [stemmer.stem(token) for token in tokens if len(token) > 2]
    return " ".join(stemmed)

def has_whole_word_match(text, word):
    if not text:
        return False
    pattern = r'\b' + re.escape(word.lower()) + r'\b'
    return bool(re.search(pattern, text.lower()))

def similarity_score(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

class BookListView(ListView):
    model = Book
    template_name = 'library/book_list.html'
    context_object_name = 'books'
    paginate_by = 12

    def get_queryset(self):
        queryset = Book.objects.all().order_by('title')
        query = self.request.GET.get('q')

        self.no_exact_match = False
        self.search_query = ''
        self.best_score = 0

        if not query:
            return queryset

        query = query.strip()
        original_query, expanded_query = expand_query_with_synonyms(query)
        search_words = expanded_query.split()

        try:
            all_books = list(Book.objects.all())

            exact_matches = []
            for book in all_books:
                for word in search_words:
                    if len(word) <= 2:
                        continue
                    if has_whole_word_match(book.title, word) or has_whole_word_match(book.author, word):
                        exact_matches.append(book)
                        break

            if exact_matches:
                self.no_exact_match = False
                self.search_query = query
                return exact_matches


            fuzzy_matches = []
            for book in all_books:
                title_score = similarity_score(query, book.title)
                author_score = similarity_score(query, book.author or "")


                title_words = re.findall(r'\w+', book.title.lower())
                word_scores = [similarity_score(word, tw) for word in search_words for tw in title_words]
                best_word_score = max(word_scores) if word_scores else 0

                best = max(title_score, author_score, best_word_score)

                if best >= 0.72:  # Threshold for spelling tolerance
                    fuzzy_matches.append((book, best))

            if fuzzy_matches:
                fuzzy_matches.sort(key=lambda x: x[1], reverse=True)
                self.no_exact_match = True
                self.search_query = query
                self.best_score = round(fuzzy_matches[0][1] * 100, 1)
                return [book for book, score in fuzzy_matches[:8]]


            self.no_exact_match = True
            self.search_query = query

            vectorizer = joblib.load('tfidf_vectorizer.pkl')
            book_texts = [
                clean_and_stem(f"{book.title} {book.description or ''}")
                for book in all_books
            ]

            book_vectors = vectorizer.transform(book_texts)
            query_vector = vectorizer.transform([clean_and_stem(expanded_query)])
            similarities = cosine_similarity(query_vector, book_vectors).flatten()

            scored_books = []
            for idx, book in enumerate(all_books):
                score = similarities[idx]
                if score > 0.03:
                    scored_books.append((book, score))

            scored_books.sort(key=lambda x: x[1], reverse=True)
            ranked_books = [book for book, score in scored_books[:8]]

            best_score = max([s for b, s in scored_books], default=0)
            self.best_score = round(best_score * 100, 1)

            return ranked_books

        except Exception as e:
            print(f"Search error: {e}")
            return queryset.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['no_exact_match'] = getattr(self, 'no_exact_match', False)
        context['search_query'] = getattr(self, 'search_query', '')
        context['best_score'] = getattr(self, 'best_score', 0)
        return context



class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'library/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Updated Stats - recalculated every time
        context['total_books'] = Book.objects.count()
        context['available_books'] = Book.objects.filter(available__gt=0).count()
        context['borrowed_books'] = Borrowing.objects.filter(
            user=self.request.user,
            status= 'approved',
            return_date__isnull=True
        ).count()

        # ML-Powered Recommendations
        try:
            vectorizer = joblib.load('tfidf_vectorizer.pkl')
            current_year = timezone.now().year

            user_borrowings = Borrowing.objects.filter(
                user=self.request.user,
                status='approved',
                return_date__isnull=True
            ).select_related('book', 'book__category')

            if user_borrowings.exists():
                borrowed_categories = set()
                borrowed_texts = []
                borrowed_ids = set()

                for b in user_borrowings:
                    borrowed_ids.add(b.book.id)
                    if b.book.category:
                        borrowed_categories.add(b.book.category.id)
                    borrowed_texts.append(f"{b.book.title} {b.book.author or ''} {b.book.description or ''}")

                candidate_books = Book.objects.filter(
                    category__id__in=borrowed_categories
                ).exclude(id__in=borrowed_ids)

                if candidate_books.count() < 6:
                    extra_books = Book.objects.exclude(
                        id__in=borrowed_ids
                    ).exclude(category__id__in=borrowed_categories)[:10]
                    candidate_books = list(candidate_books) + list(extra_books)
                else:
                    candidate_books = list(candidate_books)

                if candidate_books and borrowed_texts:
                    borrowed_vec = vectorizer.transform(borrowed_texts).mean(axis=0)
                    borrowed_vec = np.asarray(borrowed_vec)

                    candidate_texts = [
                        f"{book.title} {book.author or ''} {book.description or ''}"
                        for book in candidate_books
                    ]
                    candidate_vectors = vectorizer.transform(candidate_texts)
                    similarities = cosine_similarity(borrowed_vec, candidate_vectors).flatten()

                    scored = []
                    for book, sim in zip(candidate_books, similarities):
                        # Recency score: newer books get higher score (0.0 – 1.0)
                        if book.publication_year:
                            # Books from last 30 years get a boost; older ones get less
                            age = max(0, current_year - book.publication_year)
                            recency = max(0.0, 1.0 - (age / 30.0))
                        else:
                            recency = 0.3  # neutral score if year is unknown

                        # Final score: 70% content similarity + 30% recency
                        final_score = (0.70 * float(sim)) + (0.30 * recency)
                        scored.append((book, final_score))

                    scored.sort(key=lambda x: x[1], reverse=True)
                    recommended = [book for book, score in scored[:6]]
                else:
                    recommended = list(candidate_books)[:6]

                context['recommended_books'] = recommended
                context['recommendation_type'] = "Based on your interests & recent books"
            else:
                # New users: prefer recent available books
                context['recommended_books'] = (
                    Book.objects.filter(available__gt=0)
                    .order_by('-publication_year', '?')[:6]
                )
                context['recommendation_type'] = "Popular & Recent Books"

        except Exception as e:
            print(f"Recommendation error: {e}")
            context['recommended_books'] = Book.objects.filter(available__gt=0)[:6]
            context['recommendation_type'] = "Popular Books"

        return context

class BorrowingListView(ListView):
    model = Borrowing
    template_name = 'your_template.html'
    context_object_name = 'borrowings'

    def get_queryset(self):
        return Borrowing.objects.filter(status='approved')


@login_required
def request_return(request, pk):
    borrowing = get_object_or_404(Borrowing, pk=pk, user=request.user)

    if borrowing.status == 'approved':
        borrowing.status = 'returned_pending'
        borrowing.save()

        notify_return_request(request.user, borrowing.book)

        messages.success(request,
                         f'✅ Return request for "{borrowing.book.title}" has been submitted. Awaiting librarian approval.')
    elif borrowing.status == 'returned_pending':
        messages.info(request, "Return request is already pending approval.")
    else:
        messages.warning(request, "This book cannot be returned at this time.")

    return redirect('my_library')

from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Borrowing

@login_required
def dismiss_borrowing(request, pk):
    borrowing = get_object_or_404(Borrowing, pk=pk, user=request.user)

    if borrowing.status == 'rejected':
        borrowing.delete()
        messages.success(request, "Rejected request dismissed.")
    else:
        messages.warning(request, "Only rejected requests can be dismissed.")

    return redirect('my_library')