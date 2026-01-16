from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    monthly_budget = models.FloatField(default=0.0)
    emergency_fund_target = models.FloatField(default=0.0)
    savings_goal = models.FloatField(default=0.0)
    savings_goal_name = models.CharField(max_length=100, blank=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def save(self, *args, **kwargs):
        # Set default emergency fund (3 months of budget)
        if self.monthly_budget > 0 and self.emergency_fund_target == 0:
            self.emergency_fund_target = self.monthly_budget * 3
        super().save(*args, **kwargs)

class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    is_essential = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = "Categories"
    
    def __str__(self):
        return self.name

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    TRANSACTION_TYPES = [
        ('Income', 'Income'),
        ('Expense', 'Expense'),
        ('Withdrawal', 'Withdrawal'),
        ('Investment', 'Investment'),
    ]
    
    PAYMENT_MODES = [
        ('Cash', 'Cash'),
        ('Card', 'Card'),
        ('Online', 'Online'),
        ('UPI', 'UPI'),
        ('Bank Transfer', 'Bank Transfer'),
    ]
    
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.FloatField()
    description = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    payment_mode = models.CharField(max_length=50, choices=PAYMENT_MODES, default='Online')
    date = models.DateTimeField(default=timezone.now)
    is_consumed = models.BooleanField(default=False)  # only for Withdrawal
    is_recurring = models.BooleanField(default=False)
    recurring_frequency = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('Daily', 'Daily'),
            ('Weekly', 'Weekly'),
            ('Monthly', 'Monthly'),
            ('Yearly', 'Yearly')
        ]
    )
    
    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['type']),
            models.Index(fields=['category']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.type} - ₹{self.amount} - {self.description[:20]}"
    
    def save(self, *args, **kwargs):
        # Auto-set category if not provided (will be handled by ML prediction)
        if not self.category and self.type != 'Income':
            # In practice, you'd call your ML prediction here
            # self.category = predict_category(...)
            pass
        super().save(*args, **kwargs)