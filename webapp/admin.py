from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import CarAdminForm
from .models import Car, CarDocument, CarPayment, CarPhoto, ContactMessage, Expense, Inquiry, Profile, Purchase, Sale, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Garage', {'fields': ('role', 'phone')}),)
    list_display = ('username', 'email', 'role', 'is_staff')
    list_filter = ('role', 'is_staff')


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number')
    search_fields = ('user__username', 'user__email', 'phone_number')


class PhotoInline(admin.TabularInline):
    model = CarPhoto
    extra = 1


class PurchaseInline(admin.StackedInline):
    model = Purchase


class ExpenseInline(admin.TabularInline):
    model = Expense
    extra = 1


class SaleInline(admin.StackedInline):
    model = Sale
    can_delete = False


class CarPaymentInline(admin.TabularInline):
    model = CarPayment
    extra = 0


class DocumentInline(admin.TabularInline):
    model = CarDocument
    extra = 0


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    form = CarAdminForm
    list_display = ('__str__', 'status', 'asking_price', 'total_cost', 'profit', 'days_in_stock')
    list_filter = ('status', 'brand', 'transmission', 'fuel')
    search_fields = ('brand', 'model', 'plate_number', 'chassis_number')
    readonly_fields = ('total_expenses', 'total_cost', 'profit', 'days_in_stock')
    inlines = [PhotoInline, PurchaseInline, ExpenseInline, SaleInline, CarPaymentInline, DocumentInline]


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'car', 'kind', 'status', 'created_at')
    list_filter = ('status', 'kind')


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'topic', 'phone', 'email', 'created_at')
    list_filter = ('topic', 'created_at')
    search_fields = ('name', 'phone', 'email', 'message')
    readonly_fields = ('created_at',)