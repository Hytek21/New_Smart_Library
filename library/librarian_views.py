from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import Borrowing
from .notifications import notify_admins


@staff_member_required
def librarian_dashboard(request):
    pending_borrowings = Borrowing.objects.filter(status='pending').select_related('user', 'book')
    pending_returns = Borrowing.objects.filter(status='returned_pending').select_related('user', 'book')

    overdue = Borrowing.objects.filter(
        status='approved', due_date__lt=timezone.now()
    ).select_related('user', 'book')
    overdue_with_fines = [(b, b.calculate_fine()) for b in overdue]

    return render(request, 'library/librarian_dashboard.html', {
        'pending_borrowings': pending_borrowings,
        'pending_returns': pending_returns,
        'overdue_with_fines': overdue_with_fines,
        'total_books': Borrowing.objects.values('book').distinct().count(),
        'active_loans': Borrowing.objects.filter(status='approved').count(),
    })


@staff_member_required
def approve_borrow_request(request, pk):
    if request.method != 'POST':
        return redirect('librarian_dashboard')

    borrowing = get_object_or_404(Borrowing, pk=pk, status='pending')
    note = request.POST.get('note', '').strip()

    borrowing.status = 'approved'
    borrowing.admin_note = note
    borrowing.book.available -= 1
    borrowing.book.save()
    borrowing.save()

    messages.success(request, f'Approved "{borrowing.book.title}" for {borrowing.user.username}.')
    return redirect('librarian_dashboard')


@staff_member_required
def reject_borrow_request(request, pk):
    if request.method != 'POST':
        return redirect('librarian_dashboard')

    borrowing = get_object_or_404(Borrowing, pk=pk, status='pending')
    note = request.POST.get('note', '').strip()

    borrowing.status = 'rejected'
    borrowing.admin_note = note
    borrowing.save()

    messages.success(request, f'Rejected the request for "{borrowing.book.title}".')
    return redirect('librarian_dashboard')


@staff_member_required
def approve_return_request(request, pk):
    if request.method != 'POST':
        return redirect('librarian_dashboard')

    borrowing = get_object_or_404(Borrowing, pk=pk, status='returned_pending')
    note = request.POST.get('note', '').strip()

    borrowing.status = 'returned'
    borrowing.return_date = timezone.now()
    borrowing.fine_amount = borrowing.calculate_fine()
    if note:
        borrowing.admin_note = note
    borrowing.book.available += 1
    borrowing.book.save()
    borrowing.save()

    fine_note = f' A fine of GHS {borrowing.fine_amount} applies for late return.' if borrowing.fine_amount else ''
    messages.success(request, f'Return of "{borrowing.book.title}" confirmed.{fine_note}')
    return redirect('librarian_dashboard')


@staff_member_required
def reject_return_request(request, pk):
    if request.method != 'POST':
        return redirect('librarian_dashboard')

    borrowing = get_object_or_404(Borrowing, pk=pk, status='returned_pending')
    borrowing.status = 'approved'
    borrowing.save()

    messages.success(request, f'Return request for "{borrowing.book.title}" reverted to still-borrowed.')
    return redirect('librarian_dashboard')
