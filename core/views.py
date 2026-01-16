from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Transaction, Profile, Category
from .ml_utils import predict_category, generate_spending_advice
import json
import calendar
from django.views.decorators.http import require_GET
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# Helper functions
def calculate_balance(user):
    income = Transaction.objects.filter(user=user, type='Income').aggregate(total=Sum('amount'))['total'] or 0
    expenses = Transaction.objects.filter(user=user, type='Expense').aggregate(total=Sum('amount'))['total'] or 0
    withdrawals = Transaction.objects.filter(user=user, type='Withdrawal').aggregate(total=Sum('amount'))['total'] or 0
    return income - expenses - withdrawals

def calculate_income(user):
    return Transaction.objects.filter(user=user, type='Income').aggregate(total=Sum('amount'))['total'] or 0

def calculate_expenses(user):
    return Transaction.objects.filter(user=user, type='Expense').aggregate(total=Sum('amount'))['total'] or 0

@csrf_exempt
def analyze_transaction(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            amount = float(data.get('amount', 0))
            description = data.get('description', '')
            transaction_type = data.get('type', 'Expense')
            
            analysis = {
                'advice': generate_ai_advice(amount, description, transaction_type),
                'predicted_category': predict_category(description, amount, transaction_type, "Cash"),  # Default payment_mode
                'similar_transactions': find_similar_transactions(request.user, description, amount)
            }
            
            return JsonResponse(analysis)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)

def generate_ai_advice(amount, description, transaction_type):
    advice = []
    if transaction_type == 'Expense' and amount > 10000:
        advice.append("This is a large expense. Consider if it's essential.")
    return advice

def find_similar_transactions(user, description, amount):
    if not user.is_authenticated:
        return []
        
    keywords = description.split()[:3]
    query = Q(user=user) & Q(type='Expense')
    
    for word in keywords:
        if len(word) > 3:
            query &= Q(description__icontains=word)
    
    amount_query = Q(amount__gte=amount*0.7) & Q(amount__lte=amount*1.3)
    
    similar = Transaction.objects.filter(query | amount_query).order_by('-date')[:5]
    return [{
        'date': t.date.strftime('%Y-%m-%d'),
        'description': t.description,
        'amount': float(t.amount)
    } for t in similar]

@require_GET
def financial_analysis(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
        
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')
    balance = calculate_balance(request.user)
    income = calculate_income(request.user)
    expenses = calculate_expenses(request.user)
    
    spending_by_category = {}
    for t in transactions.filter(type='Expense'):
        category_name = t.category.name if t.category else 'Uncategorized'
        spending_by_category[category_name] = spending_by_category.get(category_name, 0) + t.amount
    
    analysis = {
        'balance': balance,
        'income': income,
        'expenses': expenses,
        'savings_rate': ((income - expenses) / income * 100) if income > 0 else 0,
        'spending_by_category': spending_by_category,
        'largest_expense': max(spending_by_category.values(), default=0),
        'recurring_expenses': sum(t.amount for t in transactions.filter(
            type='Expense', 
            category__name__in=['Subscription', 'Utilities', 'Rent', 'Loan'])
        ),
    }
    
    return JsonResponse(analysis)

# Authentication Views
def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.create(user=user)
            login(request, user)
            messages.success(request, "Account created successfully!")
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, "You've been logged out.")
    return redirect('login')

# Dashboard and Transaction Views
@login_required
def dashboard(request):
    now = timezone.now()
    current_month = now.month
    current_year = now.year
    
    profile, created = Profile.objects.get_or_create(user=request.user)
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')
    
    income = transactions.filter(type='Income').aggregate(total=Sum('amount'))['total'] or 0
    expenses = transactions.filter(type='Expense').aggregate(total=Sum('amount'))['total'] or 0
    withdrawals = transactions.filter(type='Withdrawal').aggregate(total=Sum('amount'))['total'] or 0
    balance = income - expenses - withdrawals
    
    monthly_data = get_monthly_breakdown(request.user, current_year)
    category_spending = get_category_spending(request.user, current_month, current_year)
    
    context = {
        'profile': profile,
        'transactions': transactions[:10],
        'income': income,
        'expenses': expenses,
        'withdrawals': withdrawals,
        'balance': balance,
        'monthly_data': json.dumps(monthly_data),
        'category_spending': list(category_spending),
        'financial_advice': generate_financial_advice(request.user, profile, balance),
        'upcoming_payments': get_upcoming_payments(request.user),
        'spending_suggestions': get_spending_suggestions(request.user, profile, balance),
        'payment_modes': transactions.values('payment_mode').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total'),
        'current_month': calendar.month_name[current_month],
        'current_year': current_year,
        'monthly_budget': profile.monthly_budget,
    }
    
    return render(request, 'dashboard.html', context)

@login_required
def add_transaction(request):
    categories = Category.objects.all()
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        try:
            trans_type = request.POST.get('type')
            amount = float(request.POST.get('amount', 0))
            description = request.POST.get('description', '').strip()
            payment_mode = request.POST.get('payment_mode')
            category_id = request.POST.get('category')
            
            # Validation
            if not all([trans_type, amount > 0, description, payment_mode]):
                messages.error(request, "Please fill all required fields with valid values")
                return redirect('add_transaction')
            
            transaction = Transaction(
                user=request.user,
                type=trans_type,
                amount=amount,
                description=description,
                payment_mode=payment_mode,
                date=timezone.now()
            )
            
            # Handle category
            if trans_type in ['Expense', 'Withdrawal']:
                if category_id:
                    try:
                        transaction.category = Category.objects.get(id=category_id)
                    except Category.DoesNotExist:
                        pass
                else:
                    predicted = predict_category(description, amount, trans_type, payment_mode)
                    if predicted:
                        transaction.category, _ = Category.objects.get_or_create(name=predicted)
            
            # Handle withdrawal
            if trans_type == 'Withdrawal':
                transaction.is_consumed = request.POST.get('is_consumed') == 'on'
            
            # Handle recurring
            if request.POST.get('is_recurring') == 'on':
                transaction.is_recurring = True
                transaction.recurring_frequency = request.POST.get('recurring_frequency', 'Monthly')
            
            transaction.save()
            
            # Generate advice
            if trans_type in ['Expense', 'Withdrawal']:
                advice = generate_spending_advice(
                    user=request.user,
                    amount=amount,
                    category=transaction.category.name if transaction.category else None,
                    current_balance=calculate_balance(request.user),
                    monthly_spending=get_monthly_spending(request.user),
                    monthly_budget=profile.monthly_budget
                )
                if advice:
                    messages.info(request, "\n".join(advice))
            
            messages.success(request, "Transaction added successfully!")
            return redirect('dashboard')
            
        except ValueError:
            messages.error(request, "Invalid amount entered")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
        return redirect('add_transaction')
    
    context = {
        'categories': categories,
        'current_balance': calculate_balance(request.user),
        'monthly_budget': profile.monthly_budget,
        'monthly_spending': get_monthly_spending(request.user),
        'budget_percentage': (get_monthly_spending(request.user) / profile.monthly_budget * 100) if profile.monthly_budget > 0 else 0,
    }
    return render(request, 'add_transaction.html', context)

# Financial Analysis Functions
def get_monthly_breakdown(user, year):
    monthly_data = []
    for month in range(1, 13):
        monthly_income = Transaction.objects.filter(
            user=user, type='Income', date__year=year, date__month=month
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        monthly_expense = Transaction.objects.filter(
            user=user, type='Expense', date__year=year, date__month=month
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        monthly_withdrawal = Transaction.objects.filter(
            user=user, type='Withdrawal', date__year=year, date__month=month
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        monthly_data.append({
            'month': calendar.month_abbr[month],
            'income': float(monthly_income),
            'expense': float(monthly_expense),
            'withdrawal': float(monthly_withdrawal),
            'savings': float(monthly_income - monthly_expense - monthly_withdrawal)
        })
    return monthly_data

def get_category_spending(user, month, year):
    return Transaction.objects.filter(
        user=user,
        type='Expense',
        date__year=year,
        date__month=month
    ).values('category__name').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')

def generate_financial_advice(user, profile, current_balance):
    advice = []
    now = timezone.now()
    
    monthly_income = Transaction.objects.filter(
        user=user, type='Income', date__year=now.year, date__month=now.month
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    monthly_expense = Transaction.objects.filter(
        user=user, type='Expense', date__year=now.year, date__month=now.month
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    if monthly_income > 0:
        savings_rate = (monthly_income - monthly_expense) / monthly_income * 100
        if savings_rate < 20:
            advice.append(f"Your savings rate is {savings_rate:.1f}%. Aim for at least 20%.")
    
    if profile.emergency_fund_target > 0 and current_balance < profile.emergency_fund_target:
        advice.append(f"Build your emergency fund (₹{profile.emergency_fund_target - current_balance:,.2f} to go).")
    
    if profile.monthly_budget > 0:
        budget_utilization = monthly_expense / profile.monthly_budget * 100
        if budget_utilization > 90:
            advice.append(f"You've used {budget_utilization:.1f}% of your monthly budget. Watch spending.")
    
    large_transactions = Transaction.objects.filter(
        user=user,
        type='Expense',
        date__year=now.year,
        date__month=now.month,
        amount__gte=profile.monthly_budget * 0.2 if profile.monthly_budget > 0 else 10000
    )[:3]
    
    for t in large_transactions:
        advice.append(f"Large expense: ₹{t.amount:,.2f} on {t.description} ({t.category.name if t.category else 'Uncategorized'})")
    
    return advice if advice else ["Your finances look healthy. Keep it up!"]

def get_upcoming_payments(user):
    now = timezone.now()
    upcoming = []
    
    recurring_transactions = Transaction.objects.filter(
        user=user,
        is_recurring=True,
        date__gte=now - timedelta(days=30)
    )
    
    for transaction in recurring_transactions:
        if transaction.recurring_frequency == 'Daily':
            next_date = now + timedelta(days=1)
        elif transaction.recurring_frequency == 'Weekly':
            next_date = now + timedelta(weeks=1)
        elif transaction.recurring_frequency == 'Monthly':
            next_date = now + timedelta(days=30)
        elif transaction.recurring_frequency == 'Yearly':
            next_date = now + timedelta(days=365)
        else:
            next_date = now + timedelta(days=30)
            
        upcoming.append({
            'description': transaction.description,
            'amount': transaction.amount,
            'next_payment': next_date,
            'frequency': transaction.recurring_frequency,
            'category': transaction.category.name if transaction.category else None
        })
    
    upcoming.sort(key=lambda x: x['next_payment'])
    return upcoming[:5]

def get_spending_suggestions(user, profile, current_balance):
    suggestions = []
    
    if current_balance < profile.emergency_fund_target:
        suggestions.append(f"Prioritize saving ₹{profile.emergency_fund_target - current_balance:,.2f} for emergency fund.")
    
    monthly_expense = get_monthly_spending(user)
    if profile.monthly_budget > 0 and monthly_expense < profile.monthly_budget * 0.7:
        suggestions.append(f"You have ₹{profile.monthly_budget - monthly_expense:,.2f} budget surplus.")
    
    if profile.savings_goal > 0:
        suggestions.append(f"Remember your savings goal: {profile.savings_goal_name} (₹{profile.savings_goal:,.2f})")
    
    return suggestions

def get_monthly_spending(user):
    now = timezone.now()
    return Transaction.objects.filter(
        user=user,
        type='Expense',
        date__year=now.year,
        date__month=now.month
    ).aggregate(total=Sum('amount'))['total'] or 0