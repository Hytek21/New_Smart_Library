from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Book(models.Model):
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=300)
    isbn = models.CharField(max_length=13, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    publication_year = models.PositiveIntegerField(null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    available = models.PositiveIntegerField(default=1)
    added_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def is_available(self):
        return self.available > 0

class Borrowing(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('returned_pending', 'Returned Pending'),
        ('returned', 'Returned'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    borrow_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)
    return_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_note = models.CharField(max_length=255, blank=True, help_text="Optional note left by the librarian when approving/rejecting.")
    fine_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.user.username} - {self.book.title} ({self.status})"

    def days_late(self, as_of=None):
        from django.utils import timezone
        if not self.due_date:
            return 0
        reference = as_of or self.return_date or timezone.now()
        if reference <= self.due_date:
            return 0
        return (reference - self.due_date).days

    def calculate_fine(self, as_of=None):
        from decimal import Decimal
        from django.conf import settings
        rate = Decimal(str(getattr(settings, 'FINE_PER_DAY_GHS', 1)))
        return rate * self.days_late(as_of)

class ClassificationFeedback(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    predicted_category = models.CharField(max_length=100)
    corrected_category = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback for {self.book.title} - {self.corrected_category}"

FACULTY_CHOICES = [
    ('computer_engineering', 'Faculty of Computer Engineering'),
    ('computing_information_systems', 'Faculty of Computing and Information Systems'),
    ('business_school', 'GCTU Business School'),
]


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=15, null=True, blank=True, unique=True)
    faculty = models.CharField(max_length=50, choices=FACULTY_CHOICES, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"


class OTPVerification(models.Model):
    """One-time codes used for the two-factor login step (email or phone)."""

    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('phone', 'Phone'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_codes')
    code = models.CharField(max_length=6)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.channel} OTP ({'used' if self.is_used else 'active'})"

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.created_at + timedelta(minutes=10)
