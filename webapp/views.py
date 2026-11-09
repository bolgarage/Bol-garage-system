from io import BytesIO
import mimetypes
from datetime import date
from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.cache import never_cache
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .forms import (
    CarForm,
    CarDocumentForm,
    CarPaymentForm,
    ContactMessageForm,
    EmailAuthenticationForm,
    ExpenseForm,
    GarageAccountForm,
    GarageAccountEditForm,
    InquiryForm,
    InquiryStatusForm,
    ProfileSettingsForm,
    PurchaseForm,
    SaleForm,
    SignUpForm,
)
from .models import Car, CarDocument, CarPayment, CarPhoto, ContactMessage, Expense, Inquiry, Profile, Sale
from .notifications import send_admin_notification, send_welcome_email

User = get_user_model()


def gmail_compose_url(recipient, subject, body):
    query = urlencode({
        'view': 'cm',
        'fs': '1',
        'to': recipient,
        'su': subject,
        'body': body,
    })
    return f'https://mail.google.com/mail/?{query}'


def garage_staff_required(view_func):
    @wraps(view_func)
    @never_cache
    @login_required(login_url='webapp:sign_in')
    def wrapped_view(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('webapp:home')
        return view_func(request, *args, **kwargs)

    return wrapped_view


def home(request, public=False):
    if request.user.is_authenticated and request.user.is_staff and not public:
        return redirect('webapp:dashboard')

    featured_cars = (
        Car.objects.filter(status='available')
        .prefetch_related('photos')[:3]
    )
    sold_cars = (
        Car.objects.filter(status='sold')
        .prefetch_related('photos')[:3]
    )
    return render(
        request,
        'index.html',
        {'featured_cars': featured_cars, 'sold_cars': sold_cars},
    )


@login_required
def account_settings(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={'phone_number': request.user.phone},
    )
    form = ProfileSettingsForm(
        request.POST or None,
        request.FILES or None,
        instance=profile,
        user=request.user,
    )
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated.')
            return redirect('webapp:account_settings')
        for field_name in form.errors:
            form.fields[field_name].widget.attrs.update(
                {
                    'aria-invalid': 'true',
                    'aria-describedby': f'id_{field_name}_errors',
                }
            )

    google_account = request.user.socialaccount_set.filter(provider='google').first()
    google_avatar_url = google_account.get_avatar_url() if google_account else None
    profile_avatar = (
        profile.avatar.url
        if profile.avatar
        else google_avatar_url
    )
    return render(
        request,
        'account-settings.html',
        {
            'form': form,
            'profile_avatar': profile_avatar,
            'google_avatar_url': google_avatar_url,
        },
    )


@login_required
def account_delete(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if request.POST.get('confirmation') != 'DELETE':
        messages.error(request, 'Type DELETE exactly to confirm account deletion.')
        return redirect('webapp:account_settings')

    user = request.user
    user.delete()
    logout(request)
    messages.success(request, 'Your account has been deleted.')
    return redirect('webapp:home')


def contact(request):
    form = ContactMessageForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            contact_message = form.save()
            admin_url = request.build_absolute_uri(
                f"{reverse('webapp:contact_messages')}?message={contact_message.pk}"
            )
            notification_sent = send_admin_notification(
                f'New contact message: {contact_message.get_topic_display()}',
                '\n'.join(
                    [
                        f'From: {contact_message.name}',
                        f'Phone: {contact_message.phone}',
                        f'Email: {contact_message.email or "Not provided"}',
                        f'Topic: {contact_message.get_topic_display()}',
                        '',
                        'Message:',
                        contact_message.message,
                        '',
                        f'View this message: {admin_url}',
                    ]
                ),
            )
            if notification_sent:
                messages.success(request, 'Your message has been sent to Bol Garage.')
            else:
                messages.warning(
                    request,
                    'Your message was saved, but the email alert could not be sent. '
                    'The garage can still view it in Contact messages.',
                )
            return redirect('webapp:contact')

    return render(request, 'contact.html', {'form': form})


def faqs(request):
    return render(request, 'faqs.html')


def terms(request):
    return render(request, 'terms.html')


def privacy(request):
    return render(request, 'privacy.html')


@garage_staff_required
def dashboard(request):
    today = timezone.localdate()
    cars = list(
        Car.objects.select_related('purchase', 'sale')
        .prefetch_related('expenses')
    )
    in_stock = [car for car in cars if car.status != 'sold']
    sold_cars = [car for car in cars if car.status == 'sold' and hasattr(car, 'sale')]
    sold_this_month = [
        car for car in sold_cars
        if car.sale.date_sold.year == today.year and car.sale.date_sold.month == today.month
    ]

    def car_expenses(car):
        return sum((expense.amount for expense in car.expenses.all()), Decimal('0'))

    def sale_profit(car):
        buying_price = car.purchase.buying_price if hasattr(car, 'purchase') else Decimal('0')
        return car.sale.sale_price - buying_price - car_expenses(car)

    monthly_profit_data = []
    for months_ago in range(5, -1, -1):
        month_index = today.year * 12 + today.month - 1 - months_ago
        year, zero_based_month = divmod(month_index, 12)
        month = zero_based_month + 1
        month_sales = [
            car for car in sold_cars
            if car.sale.date_sold.year == year and car.sale.date_sold.month == month
        ]
        profit = sum((sale_profit(car) for car in month_sales), Decimal('0'))
        monthly_profit_data.append({
            'month': date(year, month, 1).strftime('%b'),
            'profit': profit,
            'thousands': int(profit / Decimal('1000')),
        })
    max_monthly_profit = max(
        (abs(item['profit']) for item in monthly_profit_data),
        default=Decimal('0'),
    )
    for item in monthly_profit_data:
        item['height'] = (
            max(4, int(abs(item['profit']) / max_monthly_profit * 150))
            if max_monthly_profit
            else 0
        )
        item['is_loss'] = item['profit'] < 0

    status_classes = {
        'incoming': 'incoming',
        'repair': 'under-repair',
        'available': 'available',
        'reserved': 'reserved',
    }
    status_counts = []
    for value, label in Car.STATUS_CHOICES:
        if value == 'sold':
            continue
        status_counts.append({
            'value': value,
            'label': label,
            'css_class': status_classes[value],
            'count': sum(car.status == value for car in cars),
        })

    new_inquiries = list(
        Inquiry.objects.filter(status='new')
        .select_related('buyer', 'car')[:5]
    )
    slow_cars = sorted(
        (car for car in cars if car.status in ('available', 'reserved')),
        key=lambda car: car.days_in_stock,
        reverse=True,
    )[:4]
    for car in slow_cars:
        car.stock_cost = (
            (car.purchase.buying_price if hasattr(car, 'purchase') else Decimal('0'))
            + car_expenses(car)
        )

    context = {
        'total_stock': len(in_stock),
        'available_count': sum(car.status == 'available' for car in cars),
        'sold_this_month_count': len(sold_this_month),
        'sold_this_month_revenue': sum(
            (car.sale.sale_price for car in sold_this_month), Decimal('0')
        ),
        'sold_this_month_profit': sum(
            (sale_profit(car) for car in sold_this_month), Decimal('0')
        ),
        'all_time_profit': sum((sale_profit(car) for car in sold_cars), Decimal('0')),
        'money_tied_up': sum(
            (
                (car.purchase.buying_price if hasattr(car, 'purchase') else Decimal('0'))
                + car_expenses(car)
                for car in in_stock
            ),
            Decimal('0'),
        ),
        'new_inquiry_count': Inquiry.objects.filter(status='new').count(),
        'status_counts': status_counts,
        'monthly_profit_data': monthly_profit_data,
        'slow_cars': slow_cars,
        'new_inquiries': new_inquiries,
        'current_month': today.strftime('%B %Y'),
    }
    return render(request, 'dashboard.html', context)


@garage_staff_required
def car_financials(request, pk):
    car = get_object_or_404(
        Car.objects.select_related('purchase', 'sale')
        .prefetch_related('expenses', 'documents', 'photos', 'payments'),
        pk=pk,
    )
    purchase = car.purchase if hasattr(car, 'purchase') else None
    sale = car.sale if hasattr(car, 'sale') else None
    action = request.POST.get('action') if request.method == 'POST' else ''
    edit_expense_id = None
    edit_expense = None
    expense_edit_form = ExpenseForm()
    payment_form = CarPaymentForm()
    edit_payment_id = None
    payment_edit_form = CarPaymentForm(prefix='edit-payment')

    if request.method == 'POST':
        if action == 'status':
            status = request.POST.get('status', '')
            if status not in dict(Car.STATUS_CHOICES):
                messages.error(request, 'Choose a valid car status.')
            elif status == 'sold' and sale is None:
                messages.error(request, 'Record the sale details before setting this car to Sold.')
            elif sale is not None and status != 'sold':
                messages.error(request, 'A car with a recorded sale must remain Sold.')
            elif status == 'available' and car.asking_price <= 0:
                messages.error(request, 'Enter an asking price before making this car available.')
            else:
                car.status = status
                car.save(update_fields=['status'])
                messages.success(request, 'Car status updated.')
                return redirect('webapp:car_financials', pk=car.pk)
        elif action == 'purchase':
            form = PurchaseForm(
                request.POST,
                instance=purchase,
            )
            if form.is_valid():
                purchase = form.save(commit=False)
                purchase.car = car
                purchase.save()
                messages.success(request, 'Purchase details saved.')
                return redirect('webapp:car_financials', pk=car.pk)
            messages.error(request, 'Please correct the purchase details below.')
        elif action == 'expense':
            form = ExpenseForm(request.POST, request.FILES)
            if form.is_valid():
                expense = form.save(commit=False)
                expense.car = car
                expense.save()
                messages.success(request, 'Expense added.')
                return redirect('webapp:car_financials', pk=car.pk)
            messages.error(request, 'Please correct the expense details below.')
        elif action == 'edit_expense':
            edit_expense_id = request.POST.get('expense_id')
            edit_expense = get_object_or_404(
                Expense,
                pk=edit_expense_id,
                car=car,
            )
            form = ExpenseForm(
                request.POST,
                request.FILES,
                instance=edit_expense,
            )
            if form.is_valid():
                previous_receipt = edit_expense.receipt
                previous_receipt_name = previous_receipt.name if previous_receipt else None
                previous_receipt_storage = previous_receipt.storage if previous_receipt else None
                receipt_was_replaced = bool(
                    request.FILES.get(form.add_prefix('receipt'))
                )
                receipt_was_cleared = form.cleaned_data['receipt'] is False
                edit_expense = form.save(commit=False)
                edit_expense.car = car
                edit_expense.save()
                if previous_receipt_name and (receipt_was_replaced or receipt_was_cleared):
                    previous_receipt_storage.delete(previous_receipt_name)
                messages.success(request, 'Expense details updated.')
                return redirect('webapp:car_financials', pk=car.pk)
            expense_edit_form = form
            messages.error(request, 'Please correct the expense details below.')
        elif action == 'sale':
            form = SaleForm(request.POST, instance=sale)
            if form.is_valid():
                sale = form.save(commit=False)
                sale.car = car
                sale.save()
                if car.status != 'sold':
                    car.status = 'sold'
                    car.save(update_fields=['status'])
                messages.success(request, 'Sale details saved.')
                return redirect('webapp:car_financials', pk=car.pk)
            messages.error(request, 'Please correct the sale details below.')
        elif action == 'payment':
            payment_form = CarPaymentForm(request.POST)
            if payment_form.is_valid():
                payment = payment_form.save(commit=False)
                payment.car = car
                payment.save()
                messages.success(request, 'Payment recorded.')
                return redirect('webapp:car_financials', pk=car.pk)
            messages.error(request, 'Please correct the payment details below.')
        elif action == 'edit_payment':
            edit_payment_id = request.POST.get('payment_id')
            payment = get_object_or_404(
                CarPayment,
                pk=edit_payment_id,
                car=car,
            )
            payment_edit_form = CarPaymentForm(
                request.POST,
                instance=payment,
                prefix='edit-payment',
            )
            if payment_edit_form.is_valid():
                payment_edit_form.save()
                messages.success(request, 'Payment details updated.')
                return redirect('webapp:car_financials', pk=car.pk)
            messages.error(request, 'Please correct the payment details below.')
        elif action == 'delete_payment':
            payment = get_object_or_404(
                CarPayment,
                pk=request.POST.get('payment_id'),
                car=car,
            )
            payment.delete()
            messages.success(request, 'Payment record deleted.')
            return redirect('webapp:car_financials', pk=car.pk)
        elif action == 'document':
            form = CarDocumentForm(request.POST, request.FILES)
            if form.is_valid():
                document = form.save(commit=False)
                document.car = car
                document.save()
                messages.success(request, 'Document uploaded.')
                return redirect('webapp:car_financials', pk=car.pk)
            messages.error(request, 'Please correct the document details below.')
        else:
            messages.error(request, 'Choose a valid financial record action.')

    purchase_form = PurchaseForm(
        request.POST if action == 'purchase' else None,
        instance=purchase,
    )
    expense_form = ExpenseForm(
        request.POST if action == 'expense' else None,
        request.FILES if action == 'expense' else None,
    )
    sale_form = SaleForm(
        request.POST if action == 'sale' else None,
        instance=sale,
    )
    document_form = CarDocumentForm(
        request.POST if action == 'document' else None,
        request.FILES if action == 'document' else None,
    )
    expenses = list(car.expenses.all())
    payments = list(car.payments.all())
    expense_total = sum((expense.amount for expense in expenses), Decimal('0'))
    buying_price = purchase.buying_price if purchase else Decimal('0')
    profit_price = sale.sale_price if sale else car.asking_price
    document_groups = [
        {
            'label': label,
            'documents': [],
        }
        for value, label in CarDocument.TYPE_CHOICES
    ]
    document_groups_by_type = {
        value: group for (value, _), group in zip(
            CarDocument.TYPE_CHOICES,
            document_groups,
        )
    }
    for document in car.documents.all():
        content_type = mimetypes.guess_type(document.file.name)[0] or ''
        document.is_image = content_type.startswith('image/')
        document_groups_by_type[document.doc_type]['documents'].append(document)

    return render(
        request,
        'admin-car.html',
        {
            'car': car,
            'status_choices': Car.STATUS_CHOICES,
            'has_sale': sale is not None,
            'purchase': purchase,
            'purchase_form': purchase_form,
            'expenses': expenses,
            'edit_expense_id': edit_expense_id,
            'edit_expense': edit_expense,
            'expense_edit_form': expense_edit_form,
            'expense_total': expense_total,
            'expense_form': expense_form,
            'sale': sale,
            'sale_form': sale_form,
            'payments': payments,
            'payment_form': payment_form,
            'payment_edit_form': payment_edit_form,
            'edit_payment_id': edit_payment_id,
            'document_form': document_form,
            'document_groups': document_groups,
            'profit_price': profit_price,
            'profit_amount': profit_price - buying_price - expense_total,
            'is_final_profit': sale is not None,
        },
    )


@garage_staff_required
def car_financials_pdf(request, pk):
    car = get_object_or_404(
        Car.objects.select_related('purchase', 'sale').prefetch_related('expenses'),
        pk=pk,
    )
    purchase = car.purchase if hasattr(car, 'purchase') else None
    sale = car.sale if hasattr(car, 'sale') else None
    expenses = list(car.expenses.all())
    return car_financials_pdf_response(car, purchase, expenses, sale)


def draw_pdf_template_text(
    canvas,
    value,
    x,
    y,
    max_width,
    font_size=10,
    min_font_size=7,
    mask_width=None,
):
    text = str(value or '').replace('\r', ' ').replace('\n', ' ')
    if not text:
        return

    if mask_width:
        canvas.setFillColor(colors.white)
        canvas.rect(x - 1, y - 2, mask_width, 13, stroke=0, fill=1)
        canvas.setFillColor(colors.black)

    size = font_size
    while size > min_font_size and pdfmetrics.stringWidth(text, 'Helvetica', size) > max_width:
        size -= 0.5
    if pdfmetrics.stringWidth(text, 'Helvetica', size) > max_width:
        while text and pdfmetrics.stringWidth(text + '...', 'Helvetica', size) > max_width:
            text = text[:-1]
        text = '{}...'.format(text) if text else '...'

    canvas.setFont('Helvetica', size)
    canvas.drawString(x, y, text)


def merge_pdf_template(template_name, populate_page):
    template_path = finders.find(template_name)
    if not template_path:
        raise FileNotFoundError(
            'The PDF template could not be found: {}'.format(template_name)
        )

    with open(template_path, 'rb') as template_file:
        template_reader = PdfReader(template_file)
        if not template_reader.pages:
            raise ValueError('The PDF template has no pages: {}'.format(template_name))
        page = template_reader.pages[0]
        page_size = (
            float(page.mediabox.width),
            float(page.mediabox.height),
        )

        overlay_buffer = BytesIO()
        overlay_canvas = pdf_canvas.Canvas(overlay_buffer, pagesize=page_size)
        populate_page(overlay_canvas)
        overlay_canvas.save()
        overlay_reader = PdfReader(overlay_buffer)
        page.merge_page(overlay_reader.pages[0])

        output_buffer = BytesIO()
        writer = PdfWriter()
        writer.add_page(page)
        writer.write(output_buffer)
        return output_buffer.getvalue()


def amount_to_words(amount):
    small_numbers = (
        'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
        'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen',
        'sixteen', 'seventeen', 'eighteen', 'nineteen',
    )
    tens = (
        '', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy',
        'eighty', 'ninety',
    )

    def under_thousand(number):
        words = []
        if number >= 100:
            words.extend([small_numbers[number // 100], 'hundred'])
            number %= 100
        if number >= 20:
            words.append(tens[number // 10])
            if number % 10:
                words.append(small_numbers[number % 10])
        elif number:
            words.append(small_numbers[number])
        return ' '.join(words)

    def integer_words(number):
        if not number:
            return 'zero'
        groups = (
            (1_000_000_000, 'billion'),
            (1_000_000, 'million'),
            (1_000, 'thousand'),
            (1, ''),
        )
        words = []
        for divisor, name in groups:
            group = number // divisor
            if group:
                words.append(under_thousand(group))
                if name:
                    words.append(name)
                number %= divisor
        return ' '.join(words)

    rounded_amount = Decimal(amount).quantize(Decimal('0.01'))
    whole_amount = int(rounded_amount)
    cents = int((rounded_amount - whole_amount) * 100)
    return '{} pesos and {:02d}/100 only'.format(
        integer_words(whole_amount).capitalize(),
        cents,
    )


@garage_staff_required
def car_payment_receipt_pdf(request, pk, payment_pk):
    car = get_object_or_404(Car, pk=pk)
    payment = get_object_or_404(CarPayment, pk=payment_pk, car=car)
    created_time = timezone.localtime(payment.created_at).strftime('%I:%M %p')
    date_time = '{} {}'.format(payment.date_received.strftime('%b %d, %Y'), created_time)
    type_field = {
        'reservation': 'reservation',
        'downpayment': 'downpayment',
    }.get(payment.payment_type, 'other')
    method = payment.payment_method.strip()
    if method.casefold() == 'cash':
        method_field = 'cash'
    elif 'bank' in method.casefold() or 'gcash' in method.casefold():
        method_field = 'bank'
    else:
        method_field = 'other'
    vehicle_model = ' '.join(
        value for value in (car.brand, car.model, car.variant) if value
    )

    def populate_receipt(canvas):
        copies = (
            {
                'date': (461, 719.0, 122),
                'model': (75, 676.8, 185),
                'plate': (313, 676.8, 267),
                'type': (39, 640.5, 14),
                'amount_words': (132, 618.2, 450),
                'amount': (107, 604.1, 470),
                'method': (39, 561.7, 420),
                'reference': (105, 547.5, 480),
                'account': (110, 533.4, 474),
                'contact': (110, 519.2, 474),
                'contact_number': (117, 505.0, 464),
            },
            {
                'date': (461, 326.0, 122),
                'model': (75, 283.7, 185),
                'plate': (313, 283.7, 267),
                'type': (39, 247.5, 14),
                'amount_words': (132, 225.2, 450),
                'amount': (107, 211.0, 470),
                'method': (39, 168.6, 420),
                'reference': (105, 154.5, 480),
                'account': (110, 140.3, 474),
                'contact': (110, 126.1, 474),
                'contact_number': (117, 112.0, 464),
            },
        )
        for fields in copies:
            draw_pdf_template_text(canvas, date_time, *fields['date'])
            draw_pdf_template_text(canvas, vehicle_model, *fields['model'])
            draw_pdf_template_text(canvas, car.plate_number, *fields['plate'])
            draw_pdf_template_text(
                canvas,
                'X',
                fields['type'][0] + {'reservation': 0, 'downpayment': 178, 'other': 358}[type_field],
                fields['type'][1],
                fields['type'][2],
            )
            draw_pdf_template_text(
                canvas,
                amount_to_words(payment.amount),
                *fields['amount_words'],
                font_size=9,
            )
            draw_pdf_template_text(
                canvas,
                '{:,.2f}'.format(payment.amount),
                *fields['amount'],
            )
            if method_field == 'cash':
                draw_pdf_template_text(canvas, 'X', *fields['method'])
            elif method_field == 'bank':
                draw_pdf_template_text(
                    canvas,
                    'X',
                    fields['method'][0] + 178,
                    fields['method'][1],
                    fields['method'][2],
                )
            else:
                draw_pdf_template_text(
                    canvas,
                    'Other: {}'.format(method or 'Not provided'),
                    fields['method'][0] + 360,
                    fields['method'][1],
                    190,
                    font_size=8,
                )
            draw_pdf_template_text(canvas, payment.reference_number, *fields['reference'])
            draw_pdf_template_text(canvas, payment.account_name, *fields['account'])
            draw_pdf_template_text(canvas, payment.buyer_name, *fields['contact'])
            draw_pdf_template_text(canvas, payment.buyer_contact, *fields['contact_number'])

    pdf_content = merge_pdf_template(
        'media/Kuya Bol Garage (Acknowledgement Receipt).pdf',
        populate_receipt,
    )
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = (
        'attachment; filename="acknowledgment-receipt-BG-{}.pdf"'.format(payment.pk)
    )
    return response


@garage_staff_required
def car_sale_agreement_pdf(request, pk):
    car = get_object_or_404(Car, pk=pk)
    try:
        sale = car.sale
    except Sale.DoesNotExist:
        messages.error(request, 'Record the sale details before creating a sale agreement.')
        return redirect('webapp:car_financials', pk=car.pk)

    def populate_agreement(canvas):
        vehicle_model = ' '.join(
            value for value in (car.brand, car.model, car.variant) if value
        )
        draw_pdf_template_text(canvas, sale.date_sold.strftime('%B %d, %Y'), 501, 674.1, 98)
        draw_pdf_template_text(canvas, sale.buyer_name, 115, 640.2, 290)
        draw_pdf_template_text(
            canvas,
            sale.buyer_address,
            126,
            623.3,
            215,
            mask_width=218,
        )
        canvas.setStrokeColor(colors.HexColor('#263746'))
        canvas.setLineWidth(0.5)
        canvas.line(124.5, 620.2, 283, 620.2)
        draw_pdf_template_text(canvas, vehicle_model, 80, 453.6, 190)
        draw_pdf_template_text(canvas, str(car.year), 70, 436.5, 190)
        draw_pdf_template_text(canvas, sale.date_sold.strftime('%B %d, %Y'), 73, 385.6, 180)
        draw_pdf_template_text(canvas, '{:,.2f}'.format(sale.sale_price), 347, 385.6, 92)

    pdf_content = merge_pdf_template(
        'media/Kuya Bol Garage (Sale letter).pdf',
        populate_agreement,
    )
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = (
        'attachment; filename="vehicle-sale-agreement-car-{}.pdf"'.format(car.pk)
    )
    return response


def car_financials_pdf_response(car, purchase, expenses, sale):
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title='{} financial report'.format(car),
    )
    logo_path = finders.find('media/BG logo.png')
    if not logo_path:
        raise FileNotFoundError('The Bol Garage logo could not be found for the car report.')

    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle(
        'CarReportBrand',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#17191b'),
        spaceAfter=2,
    )
    report_title_style = ParagraphStyle(
        'CarReportTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#17191b'),
    )
    meta_style = ParagraphStyle(
        'CarReportMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#565d63'),
    )
    section_style = ParagraphStyle(
        'CarReportSection',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#17191b'),
        spaceBefore=10,
        spaceAfter=5,
    )
    cell_style = ParagraphStyle(
        'CarReportCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
    )
    label_style = ParagraphStyle(
        'CarReportLabel',
        parent=cell_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#565d63'),
    )
    header_style = ParagraphStyle(
        'CarReportTableHeader',
        parent=cell_style,
        fontName='Helvetica-Bold',
        fontSize=7.5,
        textColor=colors.white,
    )
    amount_style = ParagraphStyle(
        'CarReportAmount',
        parent=cell_style,
        alignment=TA_RIGHT,
    )

    def paragraph(value, style=cell_style):
        if value is None or value == '':
            value = '—'
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)

    def money(value):
        return 'PHP {:,.2f}'.format(value or Decimal('0'))

    def key_value_table(entries, widths=(42 * mm, 138 * mm)):
        rows = [[paragraph(label, label_style), paragraph(value)] for label, value in entries]
        table = Table(rows, colWidths=list(widths), hAlign='LEFT')
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.35, colors.HexColor('#e5e1d9')),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        return table

    brand_header = Table(
        [[
            PdfImage(logo_path, width=16 * mm, height=16 * mm, kind='proportional'),
            [
                Paragraph('Bol Garage', brand_style),
                Paragraph('Vehicle financial report', report_title_style),
            ],
        ]],
        colWidths=[19 * mm, 161 * mm],
    )
    brand_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    expenses_total = sum((expense.amount for expense in expenses), Decimal('0'))
    buying_price = purchase.buying_price if purchase else Decimal('0')
    report_price = sale.sale_price if sale else car.asking_price
    profit = report_price - buying_price - expenses_total
    content = [
        brand_header,
        Paragraph(
            'Generated {}'.format(timezone.localtime().strftime('%b %d, %Y, %I:%M %p')),
            meta_style,
        ),
        Spacer(1, 8),
        Paragraph('Vehicle details', section_style),
        key_value_table([
            ('Vehicle', car),
            ('Year / variant', '{}{}'.format(
                car.year,
                ' · {}'.format(car.variant) if car.variant else '',
            )),
            ('Plate number', car.plate_number or 'Not provided'),
            ('Engine number', car.engine_number or 'Not provided'),
            ('Chassis number', car.chassis_number or 'Not provided'),
            ('Mileage', '{:,} km'.format(car.mileage)),
            ('Transmission / fuel', '{} / {}'.format(
                car.get_transmission_display(),
                car.get_fuel_display(),
            )),
            ('Status', car.get_status_display()),
            ('Days in stock', car.days_in_stock),
        ]),
        Paragraph('Purchase', section_style),
    ]

    if purchase:
        purchase_entries = [
            ('Seller', purchase.seller_name),
            ('Seller contact', purchase.seller_contact or 'Not provided'),
            ('Date bought', purchase.date_bought.strftime('%B %d, %Y')),
            ('Buying price', money(purchase.buying_price)),
        ]
        if purchase.notes:
            purchase_entries.append(('Notes', purchase.notes))
    else:
        purchase_entries = [('Purchase', 'Purchase details have not been recorded.')]
    content.append(key_value_table(purchase_entries))

    content.append(Paragraph('Expenses', section_style))
    expense_rows = [[
        paragraph('Date', header_style),
        paragraph('Description', header_style),
        paragraph('Category', header_style),
        paragraph('Receipt', header_style),
        paragraph('Amount', header_style),
    ]]
    for expense in expenses:
        expense_rows.append([
            paragraph(expense.date.strftime('%b %d, %Y')),
            paragraph(expense.description),
            paragraph(expense.get_category_display()),
            paragraph('Attached' if expense.receipt else '—'),
            paragraph(money(expense.amount), amount_style),
        ])
    if not expenses:
        expense_rows.append([
            paragraph('No expenses recorded.'),
            '', '', '', '',
        ])
    expense_total_row = len(expense_rows)
    expense_rows.append([
        paragraph('Total expenses', label_style),
        '',
        '',
        '',
        paragraph(money(expenses_total), amount_style),
    ])
    expense_table = Table(
        expense_rows,
        colWidths=[26 * mm, 56 * mm, 34 * mm, 24 * mm, 40 * mm],
        repeatRows=1,
        hAlign='LEFT',
    )
    expense_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#17191b')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d6d2c9')),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('SPAN', (0, expense_total_row), (3, expense_total_row)),
        ('BACKGROUND', (0, expense_total_row), (-1, expense_total_row), colors.HexColor('#efede8')),
        ('LINEABOVE', (0, expense_total_row), (-1, expense_total_row), 0.8, colors.HexColor('#565d63')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor('#f7f6f3'),
        ]),
    ]))
    content.extend([
        expense_table,
        Paragraph('Sale', section_style),
    ])

    if sale:
        sale_entries = [
            ('Buyer', sale.buyer_name),
            ('Buyer contact', sale.buyer_contact or 'Not provided'),
            ('Date sold', sale.date_sold.strftime('%B %d, %Y')),
            ('Sale price', money(sale.sale_price)),
        ]
        if sale.notes:
            sale_entries.append(('Notes', sale.notes))
    else:
        sale_entries = [('Sale', 'This vehicle has not been sold.')]
    content.append(key_value_table(sale_entries))

    content.extend([
        Paragraph('Financial summary', section_style),
        key_value_table([
            ('Buying price', money(buying_price)),
            ('Total expenses', money(expenses_total)),
            ('Cost to date', money(buying_price + expenses_total)),
            ('Sale price' if sale else 'Asking price', money(report_price)),
            ('Final profit' if sale else 'Expected profit', money(profit)),
        ]),
    ])
    pdf.build(content)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="car-{}-financial-report.pdf"'.format(car.pk)
    return response


@garage_staff_required
def expense_delete(request, pk, expense_pk):
    if request.method != 'POST':
        return redirect('webapp:car_financials', pk=pk)

    car = get_object_or_404(Car, pk=pk)
    expense = get_object_or_404(Expense, pk=expense_pk, car=car)
    receipt = expense.receipt
    description = expense.description
    expense.delete()
    if receipt:
        receipt.delete(save=False)

    messages.success(request, f'Expense "{description}" was deleted.')
    return redirect('webapp:car_financials', pk=car.pk)


@garage_staff_required
def document_delete(request, pk, document_pk):
    if request.method != 'POST':
        return redirect('webapp:car_financials', pk=pk)

    car = get_object_or_404(Car, pk=pk)
    document = get_object_or_404(CarDocument, pk=document_pk, car=car)
    uploaded_file = document.file
    document.delete()
    if uploaded_file:
        uploaded_file.delete(save=False)

    messages.success(request, 'Document removed.')
    return redirect('webapp:car_financials', pk=car.pk)


@garage_staff_required
def inventory(request):
    cars = Car.objects.select_related('purchase', 'sale').prefetch_related('expenses')
    search = request.GET.get('q', '').strip()
    if search:
        cars = cars.filter(
            Q(brand__icontains=search)
            | Q(model__icontains=search)
            | Q(variant__icontains=search)
            | Q(plate_number__icontains=search)
            | Q(chassis_number__icontains=search)
        )

    status = request.GET.get('status', '')
    if status in dict(Car.STATUS_CHOICES):
        cars = cars.filter(status=status)
    cars = list(cars)
    for car in cars:
        car.garage_expenses = sum(
            (expense.amount for expense in car.expenses.all()),
            Decimal('0'),
        )
        car.garage_total_cost = car.buying_price + car.garage_expenses

    if request.GET.get('export') == 'pdf':
        return inventory_pdf_response(cars, search, status)

    context = {
        'cars': cars,
        'status_choices': Car.STATUS_CHOICES,
        'selected_status': status,
        'search_query': search,
    }
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory-results.html', context)
    return render(request, 'inventory.html', context)


def inventory_pdf_response(cars, search, status):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=9 * mm,
        leftMargin=9 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title='Bol Garage inventory',
    )
    logo_path = finders.find('media/BG logo.png')
    if not logo_path:
        raise FileNotFoundError('The Bol Garage logo could not be found for the inventory PDF.')

    styles = getSampleStyleSheet()
    meta_style = ParagraphStyle(
        'InventoryMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#565d63'),
    )
    brand_style = ParagraphStyle(
        'InventoryBrand',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#17191b'),
        spaceAfter=2,
    )
    report_title_style = ParagraphStyle(
        'InventoryReportTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#17191b'),
    )
    cell_style = ParagraphStyle(
        'InventoryCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
    )
    right_cell_style = ParagraphStyle(
        'InventoryRightCell',
        parent=cell_style,
        alignment=TA_RIGHT,
    )
    header_style = ParagraphStyle(
        'InventoryHeader',
        parent=cell_style,
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=8,
        textColor=colors.white,
    )
    brand_header = Table(
        [[
            PdfImage(logo_path, width=16 * mm, height=16 * mm, kind='proportional'),
            [
                Paragraph('Bol Garage', brand_style),
                Paragraph('Cars and inventory', report_title_style),
            ],
        ]],
        colWidths=[19 * mm, 161 * mm],
    )
    brand_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    content = [
        brand_header,
        Paragraph(
            'Bol Garage · Generated {}'.format(
                timezone.localtime().strftime('%b %d, %Y, %I:%M %p')
            ),
            meta_style,
        ),
    ]
    filter_description = []
    if status:
        filter_description.append(
            'Status: {}'.format(dict(Car.STATUS_CHOICES)[status])
        )
    if search:
        filter_description.append('Search: {}'.format(escape(search)))
    if filter_description:
        content.append(Paragraph(' · '.join(filter_description), meta_style))
    content.append(Spacer(1, 8))

    headers = [
        'Vehicle',
        'Status',
        'Buying<br/>price (PHP)',
        'Expenses<br/>(PHP)',
        'Total cost<br/>(PHP)',
        'Asking<br/>price (PHP)',
        'Days in<br/>stock',
    ]
    rows = [[Paragraph(label, header_style) for label in headers]]
    for car in cars:
        vehicle_text = escape(str(car))
        if car.plate_number:
            vehicle_text += '<br/><font color="#565d63">{}</font>'.format(
                escape(car.plate_number)
            )
        values = [
            Paragraph(vehicle_text, cell_style),
            Paragraph(escape(car.get_status_display()), cell_style),
            'PHP {:,.0f}'.format(car.buying_price),
            'PHP {:,.0f}'.format(car.garage_expenses),
            'PHP {:,.0f}'.format(car.garage_total_cost),
            'PHP {:,.0f}'.format(car.asking_price),
            str(car.days_in_stock),
        ]
        rows.append([
            value if isinstance(value, Paragraph) else Paragraph(
                escape(value),
                right_cell_style if 2 <= index <= 5 else cell_style,
            )
            for index, value in enumerate(values)
        ])
    if not cars:
        rows.append([
            Paragraph('No cars found for this inventory filter.', cell_style),
            '', '', '', '', '', '',
        ])

    table = Table(
        rows,
        colWidths=[44 * mm, 19 * mm, 26 * mm, 23 * mm, 26 * mm, 26 * mm, 22 * mm],
        repeatRows=1,
        hAlign='LEFT',
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#17191b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d6d2c9')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor('#f7f6f3'),
        ]),
    ]))
    content.append(table)
    document.build(content)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="cars-inventory.pdf"'
    return response


@garage_staff_required
def car_delete(request, pk):
    if request.method != 'POST':
        return redirect('webapp:inventory')

    car = get_object_or_404(
        Car.objects.prefetch_related('photos', 'expenses', 'documents'),
        pk=pk,
    )
    uploaded_files = [
        photo.image for photo in car.photos.all() if photo.image
    ] + [
        expense.receipt for expense in car.expenses.all() if expense.receipt
    ] + [
        document.file for document in car.documents.all() if document.file
    ]
    car_name = str(car)
    car.delete()
    for uploaded_file in uploaded_files:
        uploaded_file.delete(save=False)

    messages.success(request, f'{car_name} and its related records were permanently deleted.')
    return redirect('webapp:inventory')


@garage_staff_required
def car_manage(request, pk=None):
    car = get_object_or_404(Car, pk=pk) if pk is not None else None
    form = CarForm(
        request.POST or None,
        request.FILES or None,
        instance=car,
    )
    if request.method == 'POST' and form.is_valid():
        car = form.save()
        photos = form.cleaned_data.get('photos', [])
        if photos:
            max_order = car.photos.aggregate(max_order=Max('order'))['max_order']
            next_order = max_order + 1 if max_order is not None else 0
            for order, photo in enumerate(photos, start=next_order):
                CarPhoto.objects.create(car=car, image=photo, order=order)
        messages.success(request, f'{car} was saved.')
        return redirect('webapp:inventory')

    return render(
        request,
        'car-form.html',
        {'form': form, 'car': car},
    )


@garage_staff_required
def car_photo_delete(request, pk, photo_pk):
    if request.method != 'POST':
        return redirect('webapp:car_edit', pk=pk)

    car = get_object_or_404(Car, pk=pk)
    photo = get_object_or_404(CarPhoto, pk=photo_pk, car=car)
    image = photo.image
    photo.delete()
    image.delete(save=False)

    for order, remaining_photo in enumerate(car.photos.order_by('order', 'pk')):
        if remaining_photo.order != order:
            remaining_photo.order = order
            remaining_photo.save(update_fields=['order'])

    messages.success(request, 'Photo removed from the car listing.')
    return redirect('webapp:car_edit', pk=car.pk)


@garage_staff_required
def inquiries(request):
    all_inquiries = Inquiry.objects.select_related('buyer', 'car')
    status_counts = {
        row['status']: row['count']
        for row in all_inquiries.values('status').annotate(count=Count('pk'))
    }
    for value, _ in Inquiry.STATUS_CHOICES:
        status_counts.setdefault(value, 0)
    total_inquiries = sum(status_counts.values())
    status_tabs = [
        (value, label, status_counts[value])
        for value, label in Inquiry.STATUS_CHOICES
    ]
    status = request.GET.get('status', '')
    inquiry_list = all_inquiries
    if status in dict(Inquiry.STATUS_CHOICES):
        inquiry_list = all_inquiries.filter(status=status)
    else:
        status = ''

    inquiry_list = list(inquiry_list)
    selected_id = request.GET.get('inquiry', '')
    selected_inquiry = next(
        (inquiry for inquiry in inquiry_list if str(inquiry.pk) == selected_id),
        inquiry_list[0] if inquiry_list else None,
    )
    reply_compose_url = None
    if selected_inquiry:
        buyer_name = (
            selected_inquiry.buyer.get_full_name()
            or selected_inquiry.buyer.email
        )
        reply_compose_url = gmail_compose_url(
            selected_inquiry.buyer.email,
            f'Following up on your inquiry about {selected_inquiry.car}',
            (
                f'Hi {buyer_name},\n\n'
                f'Thank you for your {selected_inquiry.get_kind_display().lower()} '
                f'about {selected_inquiry.car}.\n\n\n'
                'Best,\nBOL Garage'
            ),
        )

    return render(
        request,
        'inquiries.html',
        {
            'inquiries': inquiry_list,
            'selected_inquiry': selected_inquiry,
            'status_choices': Inquiry.STATUS_CHOICES,
            'selected_status': status,
            'status_counts': status_counts,
            'status_tabs': status_tabs,
            'total_inquiries': total_inquiries,
            'reply_compose_url': reply_compose_url,
        },
    )


@garage_staff_required
def contact_messages(request):
    all_contact_messages = ContactMessage.objects.all()
    topic_counts = {
        row['topic']: row['count']
        for row in all_contact_messages.values('topic').annotate(count=Count('pk'))
    }
    for value, _ in ContactMessage.TOPIC_CHOICES:
        topic_counts.setdefault(value, 0)
    total_messages = sum(topic_counts.values())
    topic_tabs = [
        (value, label, topic_counts[value])
        for value, label in ContactMessage.TOPIC_CHOICES
    ]

    topic = request.GET.get('topic', '')
    contact_message_list = all_contact_messages
    if topic in dict(ContactMessage.TOPIC_CHOICES):
        contact_message_list = contact_message_list.filter(topic=topic)
    else:
        topic = ''

    selected_id = request.GET.get('message', '')
    selected_message = (
        contact_message_list.filter(pk=selected_id).first()
        if selected_id.isdecimal()
        else None
    )
    if selected_message is None:
        selected_message = contact_message_list.first()
    reply_compose_url = None
    if selected_message and selected_message.email:
        reply_compose_url = gmail_compose_url(
            selected_message.email,
            f'Following up on your {selected_message.get_topic_display().lower()} message',
            (
                f'Hi {selected_message.name},\n\n'
                f'Thank you for contacting BOL Garage about '
                f'{selected_message.get_topic_display().lower()}.\n\n\n'
                'Best,\nBOL Garage'
            ),
        )

    return render(
        request,
        'contact-messages.html',
        {
            'contact_messages': contact_message_list,
            'selected_message': selected_message,
            'selected_topic': topic,
            'topic_tabs': topic_tabs,
            'total_messages': total_messages,
            'reply_compose_url': reply_compose_url,
        },
    )


@garage_staff_required
def update_inquiry_status(request, pk):
    inquiry = get_object_or_404(Inquiry, pk=pk)
    if request.method == 'POST':
        form = InquiryStatusForm(request.POST, instance=inquiry)
        if form.is_valid():
            inquiry = form.save()
            messages.success(request, 'Inquiry status updated.')
            return redirect(
                f"{reverse('webapp:inquiries')}?status={inquiry.status}&inquiry={inquiry.pk}"
            )
        messages.error(request, 'Choose a valid inquiry status.')
    return redirect(
        f"{reverse('webapp:inquiries')}?inquiry={inquiry.pk}"
    )


@garage_staff_required
def inquiry_delete(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    inquiry = get_object_or_404(Inquiry, pk=pk)
    inquiry.delete()
    messages.success(request, 'Inquiry permanently deleted.')

    status = request.POST.get('status', '')
    if status not in dict(Inquiry.STATUS_CHOICES):
        status = ''
    return redirect(
        f"{reverse('webapp:inquiries')}?status={status}" if status else reverse('webapp:inquiries')
    )


@garage_staff_required
def contact_message_delete(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    contact_message = get_object_or_404(ContactMessage, pk=pk)
    contact_message.delete()
    messages.success(request, 'Contact message permanently deleted.')

    topic = request.POST.get('topic', '')
    if topic not in dict(ContactMessage.TOPIC_CHOICES):
        topic = ''
    return redirect(
        f"{reverse('webapp:contact_messages')}?topic={topic}"
        if topic
        else reverse('webapp:contact_messages')
    )


@garage_staff_required
def reserve_inquiry_car(request, pk):
    inquiry = get_object_or_404(Inquiry.objects.select_related('car'), pk=pk)
    if request.method != 'POST':
        return redirect(
            f"{reverse('webapp:inquiries')}?inquiry={inquiry.pk}"
        )

    car = inquiry.car
    if car.status == 'available':
        car.status = 'reserved'
        car.save(update_fields=['status'])
        messages.success(request, f'{car} is now marked Reserved.')
    elif car.status == 'reserved':
        messages.info(request, f'{car} is already marked Reserved.')
    else:
        messages.error(request, 'Only an available car can be marked Reserved.')
    return redirect(
        f"{reverse('webapp:inquiries')}?inquiry={inquiry.pk}"
    )


@garage_staff_required
def people(request):
    role = request.GET.get('role', 'buyer')
    if role not in ('buyer', 'admin'):
        role = 'buyer'

    accounts = User.objects.filter(role=role).order_by('-date_joined')
    search = request.GET.get('q', '').strip()
    if search:
        accounts = accounts.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
        )

    account_count = accounts.count()
    if request.GET.get('export') == 'pdf':
        return people_pdf_response(accounts, role, search)

    context = {
        'accounts': accounts,
        'selected_role': role,
        'search_query': search,
        'account_count': account_count,
    }
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'people-results.html', context)
    return render(request, 'people.html', context)


def people_pdf_response(accounts, role, search):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title='Bol Garage account list',
    )
    logo_path = finders.find('media/BG logo.png')
    if not logo_path:
        raise FileNotFoundError('The Bol Garage logo could not be found for the account PDF.')

    styles = getSampleStyleSheet()
    meta_style = ParagraphStyle(
        'PeopleReportMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#565d63'),
    )
    brand_style = ParagraphStyle(
        'PeopleReportBrand',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#17191b'),
        spaceAfter=2,
    )
    title_style = ParagraphStyle(
        'PeopleReportTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#17191b'),
    )
    cell_style = ParagraphStyle(
        'PeopleReportCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
    )
    header_style = ParagraphStyle(
        'PeopleReportHeader',
        parent=cell_style,
        fontName='Helvetica-Bold',
        fontSize=7.5,
        textColor=colors.white,
    )

    header = Table(
        [[
            PdfImage(logo_path, width=16 * mm, height=16 * mm, kind='proportional'),
            [
                Paragraph('Bol Garage', brand_style),
                Paragraph('People — {}'.format(
                    'Regular users' if role == 'buyer' else 'Admins'
                ), title_style),
            ],
        ]],
        colWidths=[19 * mm, 161 * mm],
    )
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    content = [
        header,
        Paragraph(
            'Generated {}'.format(
                timezone.localtime().strftime('%b %d, %Y, %I:%M %p')
            ),
            meta_style,
        ),
    ]
    if search:
        content.append(Paragraph('Search: {}'.format(escape(search)), meta_style))
    content.append(Spacer(1, 8))

    table_rows = [[
        Paragraph('Name', header_style),
        Paragraph('Email', header_style),
        Paragraph('Phone', header_style),
        Paragraph('Account status', header_style),
        Paragraph('Joined', header_style),
    ]]
    for account in accounts:
        account_status = 'Active' if account.is_active else 'Inactive'
        if account.is_superuser:
            account_status += ' · Superuser'
        table_rows.append([
            Paragraph(escape(account.get_full_name() or account.username), cell_style),
            Paragraph(escape(account.email), cell_style),
            Paragraph(escape(account.phone or '—'), cell_style),
            Paragraph(escape(account_status), cell_style),
            Paragraph(account.date_joined.strftime('%b %d, %Y'), cell_style),
        ])
    if len(table_rows) == 1:
        table_rows.append([
            Paragraph('No accounts found for this filter.', cell_style),
            '', '', '', '',
        ])

    table = Table(
        table_rows,
        colWidths=[36 * mm, 52 * mm, 30 * mm, 34 * mm, 28 * mm],
        repeatRows=1,
        hAlign='LEFT',
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#17191b')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d6d2c9')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor('#f7f6f3'),
        ]),
    ]))
    content.append(table)
    document.build(content)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="people-{}.pdf"'.format(role)
    return response


@garage_staff_required
def account_add(request):
    form = GarageAccountForm(
        request.POST or None,
        can_create_admin=request.user.is_superuser,
    )
    if request.method == 'POST' and form.is_valid():
        account = form.save()
        messages.success(request, f'Account for {account.get_full_name()} was created.')
        return redirect('webapp:people')

    return render(
        request,
        'account-form.html',
        {'form': form, 'can_create_admin': request.user.is_superuser},
    )


@garage_staff_required
def account_edit(request, pk):
    account = get_object_or_404(User, pk=pk)
    form = GarageAccountEditForm(request.POST or None, instance=account)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Account details updated.')
        return redirect('webapp:people')

    return render(
        request,
        'account-form.html',
        {
            'form': form,
            'account': account,
            'can_create_admin': request.user.is_superuser,
        },
    )


@garage_staff_required
def toggle_account_active(request, pk):
    if request.method != 'POST':
        return redirect('webapp:people')

    account = get_object_or_404(User, pk=pk)
    if account.is_superuser:
        messages.error(request, 'Superuser accounts cannot be deactivated here.')
    elif account.pk == request.user.pk and account.is_active:
        messages.error(request, 'You cannot deactivate your own account.')
    else:
        account.is_active = not account.is_active
        update_fields = ['is_active']
        if account.is_active:
            account.inactivity_reset_at = timezone.now()
            update_fields.append('inactivity_reset_at')
        account.save(update_fields=update_fields)
        action = 'activated' if account.is_active else 'deactivated'
        messages.success(request, f'{account.get_full_name() or account.email} was {action}.')
    return redirect('webapp:people')


@garage_staff_required
def account_remove(request, pk):
    if request.method != 'POST':
        return redirect('webapp:people')

    account = get_object_or_404(User, pk=pk)
    if account.is_superuser:
        messages.error(request, 'Superuser accounts cannot be removed here.')
    elif account.pk == request.user.pk:
        messages.error(request, 'You cannot remove your own account.')
    else:
        account_name = account.get_full_name() or account.email
        account.delete()
        messages.success(request, f'{account_name} was removed.')
    return redirect('webapp:people')


def car_list(request):
    cars = Car.objects.filter(status__in=['available', 'reserved']).prefetch_related('photos')

    search = request.GET.get('q', '').strip()
    if search:
        cars = cars.filter(brand__icontains=search) | cars.filter(model__icontains=search) | cars.filter(variant__icontains=search)

    brand = request.GET.get('brand', '')
    if brand:
        cars = cars.filter(brand=brand)

    transmission = request.GET.get('transmission', '')
    if transmission in dict(Car.TRANSMISSION_CHOICES):
        cars = cars.filter(transmission=transmission)

    price = request.GET.get('price', '')
    if price == 'under-500000':
        cars = cars.filter(asking_price__lt=500000)
    elif price == '500000-800000':
        cars = cars.filter(asking_price__gte=500000, asking_price__lte=800000)
    elif price == 'over-800000':
        cars = cars.filter(asking_price__gt=800000)

    year = request.GET.get('year', '')
    if year == '2020-plus':
        cars = cars.filter(year__gte=2020)
    elif year == '2018-2019':
        cars = cars.filter(year__gte=2018, year__lte=2019)
    elif year == '2017-minus':
        cars = cars.filter(year__lte=2017)

    sort = request.GET.get('sort', 'newest')
    ordering = {
        'price-low': 'asking_price',
        'price-high': '-asking_price',
        'mileage': 'mileage',
    }.get(sort, '-created_at')
    cars = cars.order_by(ordering)
    paginator = Paginator(cars, 4)
    page_obj = paginator.get_page(request.GET.get('page'))
    pagination_query = request.GET.copy()
    pagination_query.pop('page', None)

    context = {
        'cars': page_obj,
        'page_obj': page_obj,
        'pagination_query': pagination_query.urlencode(),
        'car_count': paginator.count,
        'brands': (
            Car.objects.filter(status__in=['available', 'reserved'])
            .values_list('brand', flat=True)
            .distinct()
            .order_by('brand')
        ),
        'price_choices': [
            ('under-500000', 'Under ₱500,000'),
            ('500000-800000', '₱500,000 to ₱800,000'),
            ('over-800000', 'Over ₱800,000'),
        ],
    }
    return render(request, 'cars.html', context)


def car_detail(request, pk):
    car = get_object_or_404(
        Car.objects.prefetch_related('photos'),
        pk=pk,
        status__in=['available', 'reserved'],
    )
    related_cars = (
        Car.objects.filter(status='available')
        .exclude(pk=car.pk)
        .prefetch_related('photos')[:3]
    )
    form = InquiryForm()
    return render(
        request,
        'car-detail.html',
        {'car': car, 'related_cars': related_cars, 'form': form},
    )


@login_required
def submit_inquiry(request, pk):
    car = get_object_or_404(Car, pk=pk, status='available')
    if request.method != 'POST':
        return redirect('webapp:car_detail', pk=car.pk)

    form = InquiryForm(request.POST)
    if form.is_valid():
        inquiry = form.save(commit=False)
        inquiry.car = car
        inquiry.buyer = request.user
        inquiry.save()
        admin_url = request.build_absolute_uri(
            f"{reverse('webapp:inquiries')}?status={inquiry.status}&inquiry={inquiry.pk}"
        )
        notification_sent = send_admin_notification(
            f'New {inquiry.get_kind_display().lower()}: {car}',
            '\n'.join(
                [
                    f'From: {request.user.get_full_name() or request.user.email}',
                    f'Email: {request.user.email}',
                    f'Phone: {request.user.phone or "Not provided"}',
                    f'Car: {car}',
                    f'Type: {inquiry.get_kind_display()}',
                    '',
                    'Message:',
                    inquiry.message,
                    '',
                    f'View this inquiry: {admin_url}',
                ]
            ),
        )
        if notification_sent:
            messages.success(request, 'Your request has been sent to the garage.')
        else:
            messages.warning(
                request,
                'Your request was saved, but the email alert could not be sent. '
                'The garage can still view it in Inquiries.',
            )
        return redirect('webapp:car_detail', pk=car.pk)

    related_cars = (
        Car.objects.filter(status='available')
        .exclude(pk=car.pk)
        .prefetch_related('photos')[:3]
    )
    return render(
        request,
        'car-detail.html',
        {'car': car, 'related_cars': related_cars, 'form': form},
    )


@login_required
def cancel_inquiry(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if request.user.role != 'buyer':
        raise Http404

    inquiry = get_object_or_404(
        Inquiry,
        pk=pk,
        buyer=request.user,
        status__in=['new', 'contacted'],
    )
    inquiry.status = 'cancelled'
    inquiry.save(update_fields=['status'])
    messages.success(request, 'Your inquiry has been cancelled.')

    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect('webapp:car_list')


def sign_in(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('webapp:dashboard')
        return redirect('webapp:home')

    form = EmailAuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, 'You are now signed in.')
        if user.is_staff:
            return redirect('webapp:dashboard')
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect('webapp:home')

    return render(
        request,
        'signin.html',
        {
            'login_form': form,
            'signup_form': SignUpForm(),
            'next': request.POST.get('next') or request.GET.get('next', ''),
        },
    )


def sign_up(request):
    if request.user.is_authenticated:
        return redirect('webapp:home')

    form = SignUpForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        if not user.is_staff:
            send_welcome_email(user)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, 'Your account has been created.')
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect('webapp:home')

    return render(
        request,
        'signin.html',
        {
            'login_form': EmailAuthenticationForm(),
            'signup_form': form,
            'next': request.POST.get('next') or request.GET.get('next', ''),
            'show_signup': True,
        },
    )
