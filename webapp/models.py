from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone


class User(AbstractUser):
    ROLE_CHOICES = [('buyer', 'Buyer'), ('admin', 'Admin')]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='buyer')
    phone = models.CharField(max_length=20, blank=True)
    inactivity_reset_at = models.DateTimeField(default=timezone.now)
    inactivity_warning_60_sent_for = models.DateTimeField(null=True, blank=True)
    inactivity_warning_90_sent_for = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = 'admin'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.username


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    phone_number = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='profiles/', blank=True)

    def __str__(self):
        return f'Profile for {self.user}'


class Car(models.Model):
    STATUS_CHOICES = [
        ('incoming', 'Incoming'),
        ('repair', 'Under repair'),
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('sold', 'Sold'),
    ]
    TRANSMISSION_CHOICES = [('automatic', 'Automatic'), ('manual', 'Manual')]
    FUEL_CHOICES = [('gasoline', 'Gasoline'), ('diesel', 'Diesel'), ('hybrid', 'Hybrid'), ('electric', 'Electric')]

    brand = models.CharField(max_length=50)
    model = models.CharField(max_length=80)
    variant = models.CharField(max_length=80, blank=True)
    year = models.PositiveIntegerField()
    color = models.CharField(max_length=40, blank=True)
    transmission = models.CharField(max_length=10, choices=TRANSMISSION_CHOICES, default='automatic')
    fuel = models.CharField(max_length=10, choices=FUEL_CHOICES, default='gasoline')
    mileage = models.PositiveIntegerField(help_text='In kilometers')

    # Admin-only identification
    plate_number = models.CharField(max_length=20, blank=True)
    engine_number = models.CharField(max_length=50, blank=True)
    chassis_number = models.CharField(max_length=50, blank=True)

    asking_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='incoming')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.year} {self.brand} {self.model} {self.variant}'.strip()

    # ----- money, all calculated automatically -----
    @property
    def buying_price(self):
        try:
            return self.purchase.buying_price
        except ObjectDoesNotExist:
            return 0

    @property
    def total_expenses(self):
        return self.expenses.aggregate(total=Sum('amount'))['total'] or 0

    @property
    def total_cost(self):
        return self.buying_price + self.total_expenses

    @property
    def profit(self):
        """Final profit if sold, expected profit (from asking price) if not."""
        try:
            price = self.sale.sale_price
        except ObjectDoesNotExist:
            price = self.asking_price
        return price - self.buying_price - self.total_expenses

    @property
    def days_in_stock(self):
        try:
            start = self.purchase.date_bought
        except ObjectDoesNotExist:
            start = self.created_at.date()
        return (timezone.localdate() - start).days


class CarPhoto(models.Model):
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='cars/')
    order = models.PositiveIntegerField(default=0, help_text='0 is the cover photo')

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'Photo {self.order} of {self.car}'


class Purchase(models.Model):
    car = models.OneToOneField(Car, on_delete=models.CASCADE, related_name='purchase')
    seller_name = models.CharField(max_length=100)
    seller_contact = models.CharField(max_length=100, blank=True)
    date_bought = models.DateField(default=timezone.localdate)
    buying_price = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'Purchase of {self.car}'


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('repair', 'Repair'),
        ('parts', 'Parts'),
        ('paint', 'Paint'),
        ('registration', 'Registration'),
        ('transfer', 'Transfer fees'),
        ('cleaning', 'Cleaning'),
        ('other', 'Other'),
    ]
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='expenses')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='repair')
    description = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    receipt = models.ImageField(upload_to='receipts/', blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'{self.description} ({self.amount})'


class Sale(models.Model):
    car = models.OneToOneField(Car, on_delete=models.CASCADE, related_name='sale')
    buyer_name = models.CharField(max_length=100)
    buyer_address = models.CharField(max_length=255, blank=True)
    buyer_contact = models.CharField(max_length=100, blank=True)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2)
    date_sold = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            Car.objects.filter(pk=self.car_id).exclude(status='sold').update(status='sold')

    def __str__(self):
        return f'Sale of {self.car}'


class CarPayment(models.Model):
    PAYMENT_TYPE_CHOICES = [
        ('reservation', 'Reservation fee'),
        ('downpayment', 'Downpayment'),
        ('other', 'Other payment'),
    ]

    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='payments')
    buyer_name = models.CharField(max_length=100)
    buyer_contact = models.CharField(max_length=100, blank=True)
    account_name = models.CharField(max_length=100, blank=True)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date_received = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=80)
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_received', '-created_at']

    def __str__(self):
        return f'{self.get_payment_type_display()} for {self.car} ({self.amount})'


class Inquiry(models.Model):
    KIND_CHOICES = [('inquiry', 'Inquiry'), ('reserve', 'Reserve request')]
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]

    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='inquiries')
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='inquiries')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='inquiry')
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'inquiries'

    def __str__(self):
        return f'{self.buyer} about {self.car}'


class ContactMessage(models.Model):
    TOPIC_CHOICES = [
        ('car', 'Question about a car'),
        ('visit', 'Plan a visit'),
        ('selling', 'Selling my vehicle'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    topic = models.CharField(max_length=10, choices=TOPIC_CHOICES, default='other')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'contact message'
        verbose_name_plural = 'contact messages'

    def __str__(self):
        return f'{self.name} — {self.get_topic_display()}'


class CarDocument(models.Model):
    TYPE_CHOICES = [
        ('orcr', 'OR/CR'),
        ('deed_seller', 'Deed of sale (from seller)'),
        ('deed_buyer', 'Deed of sale (to buyer)'),
        ('receipt', 'Receipt'),
        ('other', 'Other'),
    ]
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other')
    file = models.FileField(upload_to='documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.get_doc_type_display()} for {self.car}'