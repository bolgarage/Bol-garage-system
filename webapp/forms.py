import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Car, CarDocument, CarPayment, ContactMessage, Expense, Inquiry, Profile, Purchase, Sale

User = get_user_model()


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(
            attrs={
                'autocomplete': 'email',
                'placeholder': 'e.g. name@example.com',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password'].widget.attrs['placeholder'] = 'Enter your password'

    def clean_username(self):
        email = self.cleaned_data['username']
        users = User.objects.filter(email__iexact=email)
        if users.count() == 1:
            return users.get().get_username()
        return email


class SignUpForm(UserCreationForm):
    full_name = forms.CharField(
        max_length=150,
        label='Full name',
        widget=forms.TextInput(attrs={'placeholder': 'e.g. Juan Dela Cruz'}),
    )
    email = forms.EmailField(
        max_length=150,
        widget=forms.EmailInput(attrs={'placeholder': 'e.g. name@example.com'}),
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 09123456789'}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('email', 'phone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs['placeholder'] = 'Create a password'
        self.fields['password2'].widget.attrs['placeholder'] = 'Re-enter your password'

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('This email cannot be used for an account.')
        return email

    def clean_full_name(self):
        full_name = self.cleaned_data['full_name'].strip()
        if not full_name:
            raise forms.ValidationError('Enter your full name.')
        return full_name

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        user.email = self.cleaned_data['email']
        user.phone = self.cleaned_data['phone']
        name_parts = self.cleaned_data['full_name'].strip().split(maxsplit=1)
        user.first_name = name_parts[0] if name_parts else ''
        user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        if commit:
            user.save()
        return user


class ProfileSettingsForm(forms.ModelForm):
    clear_avatar = forms.BooleanField(required=False)
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'given-name'}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'family-name'}),
    )

    class Meta:
        model = Profile
        fields = ('avatar', 'phone_number')
        widgets = {
            'avatar': forms.FileInput(
                attrs={
                    'accept': 'image/*',
                    'class': 'sr-only settings-avatar-input',
                    'data-avatar-input': '',
                },
            ),
            'phone_number': forms.TextInput(
                attrs={
                    'autocomplete': 'tel',
                    'inputmode': 'tel',
                    'placeholder': 'e.g. +63 912 345 6789',
                }
            ),
        }

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.order_fields(['avatar', 'first_name', 'last_name', 'phone_number'])
        self.fields['avatar'].label = 'Profile photo'
        self.fields['avatar'].help_text = 'Select the camera icon to upload a profile photo.'
        self.fields['first_name'].initial = user.first_name
        self.fields['last_name'].initial = user.last_name

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        uploaded_avatar = self.files.get(self.add_prefix('avatar'))
        if uploaded_avatar and uploaded_avatar.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Choose an image smaller than 5 MB.')
        return avatar

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number'].strip()
        if not phone_number:
            return ''
        if not re.fullmatch(r'[0-9 ()+-]+', phone_number):
            raise forms.ValidationError(
                'Use only digits, spaces, +, -, and parentheses.'
            )
        digit_count = sum('0' <= character <= '9' for character in phone_number)
        if not 7 <= digit_count <= 15:
            raise forms.ValidationError('Enter a phone number with 7 to 15 digits.')
        return phone_number

    def save(self, commit=True):
        profile = super().save(commit=False)
        if self.cleaned_data.get('clear_avatar') and not self.files.get(
            self.add_prefix('avatar')
        ):
            profile.avatar = ''
        self.user.first_name = self.cleaned_data['first_name'].strip()
        self.user.last_name = self.cleaned_data['last_name'].strip()
        self.user.phone = profile.phone_number
        if commit:
            self.user.save(update_fields=['first_name', 'last_name', 'phone'])
            profile.save()
        return profile


class InquiryForm(forms.ModelForm):
    class Meta:
        model = Inquiry
        fields = ('kind', 'message')
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
        }


class ContactMessageForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ('name', 'phone', 'email', 'topic', 'message')
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Your name', 'autocomplete': 'name'}),
            'phone': forms.TelInput(attrs={'placeholder': '09XX XXX XXXX', 'autocomplete': 'tel'}),
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autocomplete': 'email'}),
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Tell us how we can help.'}),
        }


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleImageInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleImageField, self).clean(file, initial) for file in files]


class CarStatusValidationMixin:
    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        asking_price = cleaned_data.get('asking_price')

        if status == 'available' and (asking_price is None or asking_price <= 0):
            self.add_error('asking_price', 'Enter an asking price before making this car available.')

        if self.instance.pk:
            has_sale = hasattr(self.instance, 'sale')
            if status == 'sold' and not has_sale:
                self.add_error('status', 'Record the sale details before setting this car to Sold.')
            elif has_sale and status != 'sold':
                self.add_error('status', 'A car with a recorded sale must remain Sold.')
        elif status == 'sold':
            self.add_error('status', 'Record the sale after creating the car.')

        return cleaned_data


class CarForm(CarStatusValidationMixin, forms.ModelForm):
    photos = MultipleImageField(
        required=False,
        label='Vehicle photos',
        help_text='Select multiple exterior and interior photos. The first photo on a new car is the cover image.',
    )

    class Meta:
        model = Car
        fields = (
            'brand',
            'model',
            'variant',
            'year',
            'color',
            'transmission',
            'fuel',
            'mileage',
            'plate_number',
            'engine_number',
            'chassis_number',
            'asking_price',
            'description',
            'status',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields([
            'brand',
            'model',
            'variant',
            'year',
            'color',
            'transmission',
            'fuel',
            'mileage',
            'plate_number',
            'engine_number',
            'chassis_number',
            'asking_price',
            'description',
            'status',
            'photos',
        ])

class CarAdminForm(CarStatusValidationMixin, forms.ModelForm):
    class Meta:
        model = Car
        fields = '__all__'


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ('seller_name', 'seller_contact', 'date_bought', 'buying_price', 'notes')
        widgets = {
            'date_bought': forms.DateInput(attrs={'type': 'date'}),
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ('description', 'category', 'date', 'amount', 'receipt')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = (
            'buyer_name',
            'buyer_address',
            'buyer_contact',
            'sale_price',
            'date_sold',
            'notes',
        )
        widgets = {
            'date_sold': forms.DateInput(attrs={'type': 'date'}),
        }


class CarPaymentForm(forms.ModelForm):
    class Meta:
        model = CarPayment
        fields = (
            'buyer_name',
            'buyer_contact',
            'account_name',
            'payment_type',
            'amount',
            'date_received',
            'payment_method',
            'reference_number',
            'notes',
        )
        widgets = {
            'date_received': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Enter an amount greater than zero.')
        return amount


class CarDocumentForm(forms.ModelForm):
    class Meta:
        model = CarDocument
        fields = ('doc_type', 'file')


class InquiryStatusForm(forms.ModelForm):
    class Meta:
        model = Inquiry
        fields = ('status',)


class GarageAccountForm(UserCreationForm):
    full_name = forms.CharField(max_length=150, label='Full name')
    email = forms.EmailField(max_length=150)
    phone = forms.CharField(max_length=20, required=False)
    role = forms.ChoiceField(choices=(('buyer', 'Regular user'),))

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('email', 'phone')

    def __init__(self, *args, can_create_admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        if can_create_admin:
            self.fields['role'].choices = (
                ('buyer', 'Regular user'),
                ('admin', 'Admin'),
            )

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('This email cannot be used for an account.')
        return email

    def clean_full_name(self):
        full_name = self.cleaned_data['full_name'].strip()
        if not full_name:
            raise forms.ValidationError('Enter the account holder’s full name.')
        return full_name

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        user.email = self.cleaned_data['email']
        user.phone = self.cleaned_data['phone']
        user.role = self.cleaned_data['role']
        user.is_staff = user.role == 'admin'
        name_parts = self.cleaned_data['full_name'].split(maxsplit=1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        if commit:
            user.save()
        return user


class GarageAccountEditForm(forms.ModelForm):
    full_name = forms.CharField(max_length=150, label='Full name')
    email = forms.EmailField(max_length=150)

    class Meta:
        model = User
        fields = ('email', 'phone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['full_name'].initial = self.instance.get_full_name()

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        duplicates = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError('An account with this email already exists.')
        username_duplicates = User.objects.filter(username__iexact=email).exclude(pk=self.instance.pk)
        if username_duplicates.exists():
            raise forms.ValidationError('This email cannot be used for this account.')
        return email

    def clean_full_name(self):
        full_name = self.cleaned_data['full_name'].strip()
        if not full_name:
            raise forms.ValidationError('Enter the account holder’s full name.')
        return full_name

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.username = self.cleaned_data['email']
        name_parts = self.cleaned_data['full_name'].split(maxsplit=1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        if commit:
            user.save()
        return user
