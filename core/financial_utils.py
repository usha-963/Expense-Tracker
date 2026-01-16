from django.db.models import Sum
from .models import Transaction

def calculate_balance(user):
    """
    Calculate the current balance for a user
    """
    income = Transaction.objects.filter(
        user=user,
        type='Income'
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    expenses = Transaction.objects.filter(
        user=user,
        type='Expense'
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    withdrawals = Transaction.objects.filter(
        user=user,
        type='Withdrawal'
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    return income - expenses - withdrawals

def calculate_income(user, period=None):
    """
    Calculate total income for a user
    Optional period filter (e.g., 'month', 'year')
    """
    queryset = Transaction.objects.filter(
        user=user,
        type='Income'
    )
    
    if period == 'month':
        from django.utils import timezone
        from datetime import timedelta
        last_month = timezone.now() - timedelta(days=30)
        queryset = queryset.filter(date__gte=last_month)
    elif period == 'year':
        from django.utils import timezone
        from datetime import timedelta
        last_year = timezone.now() - timedelta(days=365)
        queryset = queryset.filter(date__gte=last_year)
    
    return queryset.aggregate(Sum('amount'))['amount__sum'] or 0

def calculate_expenses(user, period=None):
    """
    Calculate total expenses for a user
    Optional period filter (e.g., 'month', 'year')
    """
    queryset = Transaction.objects.filter(
        user=user,
        type='Expense'
    )
    
    if period == 'month':
        from django.utils import timezone
        from datetime import timedelta
        last_month = timezone.now() - timedelta(days=30)
        queryset = queryset.filter(date__gte=last_month)
    elif period == 'year':
        from django.utils import timezone
        from datetime import timedelta
        last_year = timezone.now() - timedelta(days=365)
        queryset = queryset.filter(date__gte=last_year)
    
    return queryset.aggregate(Sum('amount'))['amount__sum'] or 0

def get_monthly_budget(user):
    """
    Get the user's monthly budget if set
    """
    from .models import UserProfile
    try:
        profile = UserProfile.objects.get(user=user)
        return profile.monthly_budget
    except UserProfile.DoesNotExist:
        return None

def calculate_remaining_budget(user):
    """
    Calculate remaining budget for the current month
    """
    budget = get_monthly_budget(user)
    if budget is None:
        return None
    
    expenses = calculate_expenses(user, period='month')
    return budget - expenses