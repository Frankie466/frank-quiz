from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
import re
import random
import string

class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number, pin, **extra_fields):
        # Validate phone number format
        full_phone = self.normalize_phone_number(phone_number)
        if not self.is_valid_phone_number(full_phone):
            raise ValueError('Phone number must be in format 7XXXXXXXX or +2547XXXXXXXX')
        
        # Validate PIN is 4 digits
        if not self.is_valid_pin(pin):
            raise ValueError('PIN must be exactly 4 digits')
            
        # Check if user already exists
        if CustomUser.objects.filter(phone_number=full_phone).exists():
            raise ValueError('Phone number already registered')
            
        user = self.model(phone_number=full_phone, **extra_fields)
        user.set_pin(pin)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, pin, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_premium', True)
        extra_fields.setdefault('balance', 1000.00)
        return self.create_user(phone_number, pin, **extra_fields)
    
    def normalize_phone_number(self, phone_number):
        """Convert phone number to standard +254 format"""
        if not phone_number:
            raise ValueError('Phone number is required')
            
        phone_number = str(phone_number).strip()
        
        # Remove any spaces, dashes, etc.
        phone_number = re.sub(r'[^\d+]', '', phone_number)
        
        # If it starts with 0, replace with +254
        if phone_number.startswith('0'):
            phone_number = '+254' + phone_number[1:]
        # If it starts with 7 or 1 (without country code), add +254
        elif phone_number.startswith('7') or phone_number.startswith('1'):
            phone_number = '+254' + phone_number
        # If it already has +254, leave as is
        elif phone_number.startswith('+254'):
            pass
        else:
            raise ValueError('Invalid phone number format')
            
        return phone_number
    
    def is_valid_phone_number(self, phone_number):
        """Validate Kenyan phone number format"""
        pattern = r'^\+254[17]\d{8}$'
        return bool(re.match(pattern, phone_number))
    
    def is_valid_pin(self, pin):
        """Validate PIN is exactly 4 digits"""
        return bool(re.match(r'^\d{4}$', str(pin)))

class CustomUser(AbstractBaseUser, PermissionsMixin):
    # Authentication fields
    phone_number = models.CharField(max_length=15, unique=True)
    pin = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    
    # Additional fields for business logic
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    is_premium = models.BooleanField(default=False)
    referral_code = models.CharField(max_length=10, unique=True, blank=True)
    total_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    surveys_completed = models.IntegerField(default=0)
    
    # Referral system
    referred_by = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='referrals'
    )
    referral_bonus_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # Track important dates
    last_login = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(null=True, blank=True)
    premium_activated_date = models.DateTimeField(null=True, blank=True)
    
    # Profile information (optional)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    
    objects = CustomUserManager()
    
    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['pin']  # Add pin to required fields
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']
    
    def __str__(self):
        return self.phone_number
    
    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self.generate_referral_code()
        super().save(*args, **kwargs)
    
    def generate_referral_code(self):
        """Generate unique referral code"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not CustomUser.objects.filter(referral_code=code).exists():
                return code
    
    def set_pin(self, raw_pin):
        from django.contrib.auth.hashers import make_password
        self.pin = make_password(raw_pin)
    
    def check_pin(self, raw_pin):
        from django.contrib.auth.hashers import check_password
        return check_password(raw_pin, self.pin)
    
    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.phone_number
    
    @property
    def display_name(self):
        """Display name for UI"""
        if self.first_name:
            return self.first_name
        # Show last 4 digits of phone number
        return f"User {self.phone_number[-4:]}"
    
    def activate_premium(self):
        """Activate premium membership and add Ksh 500 bonus"""
        from django.db import transaction
        
        with transaction.atomic():
            self.is_premium = True
            self.premium_activated_date = timezone.now()
            
            # Add Ksh 500 bonus to balance
            bonus_amount = 500.00
            self.balance += bonus_amount
            self.save()
            
            # Create transaction record for premium activation bonus
            Transaction.objects.create(
                user=self,
                amount=bonus_amount,
                transaction_type='bonus',
                description='Premium Activation Bonus'
            )
            
            # Also create a transaction for the premium activation itself
            Transaction.objects.create(
                user=self,
                amount=0.00,  # The payment is handled separately via M-Pesa
                transaction_type='premium',
                description='Premium Membership Activation'
            )
    
    def add_earning(self, amount, description="Survey completion"):
        """Add earnings to user balance"""
        from django.db import transaction
        
        with transaction.atomic():
            self.balance += amount
            self.total_earned += amount
            self.save()
            
            # Create transaction record
            Transaction.objects.create(
                user=self,
                amount=amount,
                transaction_type='earning',
                description=description
            )
    
    def withdraw(self, amount):
        """Process withdrawal from balance"""
        from django.db import transaction
        
        if amount > self.balance:
            raise ValueError("Insufficient balance")
        
        with transaction.atomic():
            self.balance -= amount
            self.save()
            
            # Create withdrawal transaction record
            Transaction.objects.create(
                user=self,
                amount=amount,
                transaction_type='withdrawal',
                description='M-Pesa Withdrawal'
            )
    
    def add_referral_bonus(self, amount):
        """Add referral bonus"""
        self.balance += amount
        self.referral_bonus_earned += amount
        self.save()
        
        Transaction.objects.create(
            user=self,
            amount=amount,
            transaction_type='bonus',
            description='Referral Bonus'
        )

class MpesaTransaction(models.Model):
    """Model to track M-Pesa payments for premium activation"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='mpesa_transactions')
    phone_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    checkout_request_id = models.CharField(max_length=100, unique=True)
    merchant_request_id = models.CharField(max_length=100)
    mpesa_receipt = models.CharField(max_length=50, blank=True, null=True)
    account_reference = models.CharField(max_length=100)
    transaction_desc = models.CharField(max_length=200)
    result_code = models.IntegerField(null=True, blank=True)
    result_desc = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    transaction_date = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'M-Pesa Transaction'
        verbose_name_plural = 'M-Pesa Transactions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.phone_number} - Ksh {self.amount} - {self.status}"
    
    def mark_as_completed(self, mpesa_receipt=None, result_code=0, result_desc="Success"):
        """Mark transaction as completed and activate premium"""
        from django.db import transaction
        
        with transaction.atomic():
            self.status = 'COMPLETED'
            self.result_code = result_code
            self.result_desc = result_desc
            
            if mpesa_receipt:
                self.mpesa_receipt = mpesa_receipt
            
            self.save()
            
            # Activate premium for user if not already active
            if not self.user.is_premium:
                self.user.activate_premium()
            
            # Create a payment transaction record
            Transaction.objects.create(
                user=self.user,
                amount=self.amount,
                transaction_type='premium',
                description=f'Premium Activation Payment - M-Pesa Receipt: {mpesa_receipt or "N/A"}'
            )
    
    def mark_as_failed(self, result_code, result_desc):
        """Mark transaction as failed"""
        self.status = 'FAILED'
        self.result_code = result_code
        self.result_desc = result_desc
        self.save()

class Survey(models.Model):
    SURVEY_CATEGORIES = [
        ('consumer', 'Consumer Products'),
        ('technology', 'Technology'),
        ('finance', 'Finance & Banking'),
        ('health', 'Health & Wellness'),
        ('entertainment', 'Entertainment'),
        ('shopping', 'Shopping Habits'),
        ('social', 'Social Media'),
        ('other', 'Other'),
    ]
    
    DIFFICULTY_LEVELS = [
        ('easy', 'Easy (2-5 mins)'),
        ('medium', 'Medium (5-10 mins)'),
        ('premium', 'Premium (10-15 mins)'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    reward_amount = models.DecimalField(max_digits=6, decimal_places=2)
    estimated_time = models.IntegerField(help_text="Estimated time in minutes")
    category = models.CharField(max_length=100, choices=SURVEY_CATEGORIES, default='consumer')
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_LEVELS, default='easy')
    is_active = models.BooleanField(default=True)
    is_premium_only = models.BooleanField(default=False)
    questions_count = models.IntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Survey'
        verbose_name_plural = 'Surveys'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - Ksh {self.reward_amount}"

class UserSurvey(models.Model):
    STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('started', 'Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('abandoned', 'Abandoned'),
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='user_surveys')
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='user_surveys')
    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    earnings = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='assigned')
    current_question = models.IntegerField(default=0)
    
    class Meta:
        verbose_name = 'User Survey'
        verbose_name_plural = 'User Surveys'
        unique_together = ['user', 'survey']
        ordering = ['-assigned_at']
    
    def __str__(self):
        return f"{self.user.phone_number} - {self.survey.title}"

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('earning', 'Survey Earnings'),
        ('withdrawal', 'Withdrawal'),
        ('bonus', 'Bonus'),
        ('referral', 'Referral Bonus'),
        ('premium', 'Premium Activation'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    description = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    mpesa_receipt = models.CharField(max_length=50, blank=True, null=True)
    mpesa_phone = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.phone_number} - {self.transaction_type} - Ksh {self.amount}"

class WithdrawalRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    mpesa_phone = models.CharField(max_length=15)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    mpesa_receipt = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Withdrawal Request'
        verbose_name_plural = 'Withdrawal Requests'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.phone_number} - Ksh {self.amount} - {self.status}"