from django.urls import path
from django.views.generic import RedirectView
from django.contrib.auth.views import LogoutView

from . import views

app_name = 'webapp'

urlpatterns = [
    path('', views.home, name='home'),
    path('public/', views.home, {'public': True}, name='public_home'),
    path('account/settings/', views.account_settings, name='account_settings'),
    path('account/delete/', views.account_delete, name='account_delete'),
    path('contact/', views.contact, name='contact'),
    path('faqs/', views.faqs, name='faqs'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('garage/', views.dashboard, name='dashboard'),
    path('garage/cars/', views.inventory, name='inventory'),
    path('garage/cars/add/', views.car_manage, name='car_add'),
    path('garage/cars/<int:pk>/financials/export.pdf', views.car_financials_pdf, name='car_financials_pdf'),
    path('garage/cars/<int:pk>/financials/', views.car_financials, name='car_financials'),
    path('garage/cars/<int:pk>/sale-agreement.pdf', views.car_sale_agreement_pdf, name='car_sale_agreement_pdf'),
    path('garage/cars/<int:pk>/payments/<int:payment_pk>/receipt.pdf', views.car_payment_receipt_pdf, name='car_payment_receipt_pdf'),
    path('garage/cars/<int:pk>/delete/', views.car_delete, name='car_delete'),
    path('garage/cars/<int:pk>/expenses/<int:expense_pk>/delete/', views.expense_delete, name='expense_delete'),
    path('garage/cars/<int:pk>/documents/<int:document_pk>/delete/', views.document_delete, name='document_delete'),
    path('garage/cars/<int:pk>/edit/', views.car_manage, name='car_edit'),
    path('garage/cars/<int:pk>/photos/<int:photo_pk>/delete/', views.car_photo_delete, name='car_photo_delete'),
    path('garage/inquiries/', views.inquiries, name='inquiries'),
    path('garage/contact-messages/', views.contact_messages, name='contact_messages'),
    path('garage/contact-messages/<int:pk>/delete/', views.contact_message_delete, name='contact_message_delete'),
    path('garage/inquiries/<int:pk>/status/', views.update_inquiry_status, name='inquiry_status'),
    path('garage/inquiries/<int:pk>/delete/', views.inquiry_delete, name='inquiry_delete'),
    path('garage/inquiries/<int:pk>/reserve-car/', views.reserve_inquiry_car, name='inquiry_reserve_car'),
    path('garage/people/', views.people, name='people'),
    path('garage/people/add/', views.account_add, name='account_add'),
    path('garage/people/<int:pk>/edit/', views.account_edit, name='account_edit'),
    path('garage/people/<int:pk>/toggle-active/', views.toggle_account_active, name='account_toggle_active'),
    path('garage/people/<int:pk>/remove/', views.account_remove, name='account_remove'),
    path('cars/', views.car_list, name='car_list'),
    path('cars/<int:pk>/', views.car_detail, name='car_detail'),
    path('cars/<int:pk>/inquiry/', views.submit_inquiry, name='submit_inquiry'),
    path('cars/inquiries/<int:pk>/cancel/', views.cancel_inquiry, name='cancel_inquiry'),
    path('signin/', views.sign_in, name='sign_in'),
    path('signup/', views.sign_up, name='sign_up'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path(
        'cars/signin.html',
        RedirectView.as_view(pattern_name='webapp:sign_in', permanent=False),
        name='legacy_sign_in',
    ),
]
