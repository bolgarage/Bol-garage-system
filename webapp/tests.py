from datetime import timedelta
from decimal import Decimal
from email.message import MIMEPart
from io import BytesIO
import os
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from allauth.account.models import EmailAddress
from allauth.core.context import request_context
from allauth.socialaccount.internal.flows.signup import process_signup
from allauth.socialaccount.models import SocialAccount, SocialLogin
from allauth.socialaccount.providers.google.provider import GoogleProvider
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from pypdf import PdfReader

from .adapters import GarageAccountAdapter, GarageSocialAccountAdapter
from .models import Car, CarDocument, CarPayment, CarPhoto, ContactMessage, Expense, Inquiry, Profile, Purchase, Sale

User = get_user_model()


class PublicPagesTests(TestCase):
    def setUp(self):
        self.car = Car.objects.create(
            brand='Toyota',
            model='Vios',
            variant='1.3 E',
            year=2018,
            transmission='automatic',
            fuel='gasoline',
            mileage=58000,
            asking_price=465000,
            status='available',
            description='Well maintained.',
        )

    def test_homepage_loads(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Good used cars.')
        self.assertContains(response, 'rel="icon" type="image/png"')
        self.assertTemplateUsed(response, 'index.html')
        self.assertContains(response, 'Toyota Vios')
        self.assertContains(response, 'media/Bol.jpg')
        self.assertContains(response, 'Bol, owner of Bol Garage')
        self.assertNotContains(response, 'Find your car')
        self.assertContains(response, 'We buy vehicles and accept consignments.')
        self.assertContains(response, 'Sell your car')
        self.assertContains(response, 'Message us on Facebook')
        self.assertContains(response, '₱465,000')
        self.assertLess(
            response.content.index(b'Recently sold'),
            response.content.index(b'Want to sell your car?'),
        )
        self.assertNotContains(response, 'id="contact"')
        self.assertContains(response, 'site-footer-logo')
        self.assertContains(response, 'alt="Bol Garage logo"')
        self.assertContains(response, 'media/BG%20logo.png')
        self.assertContains(response, 'aria-controls="site-navigation"')
        self.assertContains(response, 'navigation.js')
        self.assertContains(response, 'href="/" class="active" aria-current="page">Home</a>')
        self.assertContains(response, 'class="nav-cta">Sign in</a>')
        self.assertNotContains(response, 'data-profile-menu-toggle')

    def test_authenticated_navbar_shows_profile_menu_with_initial_fallback(self):
        user = User.objects.create_user(
            username='jane@example.com',
            email='jane@example.com',
            first_name='Jane',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('webapp:home'))

        self.assertContains(response, 'data-profile-menu-toggle')
        self.assertContains(response, 'aria-haspopup="true"')
        self.assertContains(response, 'aria-expanded="false"')
        self.assertContains(response, 'class="profile-avatar-initial" aria-hidden="true">J')
        self.assertContains(response, 'Jane')
        self.assertContains(response, 'jane@example.com')
        self.assertContains(response, reverse('webapp:account_settings'))
        self.assertContains(response, 'action="{}"'.format(reverse('account_logout')))
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'profile-menu.js')
        self.assertNotContains(response, 'class="nav-cta">Sign in</a>')
        self.assertNotContains(response, 'Garage dashboard')

    def test_staff_navbar_links_to_garage_dashboard(self):
        admin = User.objects.create_superuser(
            username='bolgarage123@gmail.com',
            email='bolgarage123@gmail.com',
            password='SolidPassword2026!',
            first_name='Kuya',
            last_name='Bol',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('webapp:public_home'))

        self.assertContains(response, 'Garage dashboard')
        self.assertContains(response, reverse('webapp:dashboard'))
        self.assertContains(response, 'Kuya')
        self.assertContains(response, f'href="{reverse("webapp:public_home")}" class="active" aria-current="page">Home</a>')

    def test_staff_opening_site_root_is_redirected_to_dashboard(self):
        admin = User.objects.create_superuser(
            username='root-admin@example.com',
            email='root-admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('webapp:home'))

        self.assertRedirects(response, reverse('webapp:dashboard'))

    def test_staff_can_open_public_home_page_explicitly(self):
        admin = User.objects.create_superuser(
            username='public-site-admin@example.com',
            email='public-site-admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('webapp:public_home'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'index.html')
    def test_authenticated_google_avatar_uses_profile_picture(self):
        user = User.objects.create_user(
            username='google@example.com',
            email='google@example.com',
        )
        SocialAccount.objects.create(
            user=user,
            provider='google',
            uid='google-avatar',
            extra_data={'picture': 'https://example.test/avatar.png'},
        )
        self.client.force_login(user)

        response = self.client.get(reverse('webapp:home'))

        self.assertContains(response, 'src="https://example.test/avatar.png"')
        self.assertNotContains(response, 'class="profile-avatar-initial"')

    def test_uploaded_profile_photo_replaces_google_avatar(self):
        user = User.objects.create_user(
            username='custom-avatar@example.com',
            email='custom-avatar@example.com',
            first_name='Custom',
        )
        SocialAccount.objects.create(
            user=user,
            provider='google',
            uid='google-custom-avatar',
            extra_data={'picture': 'https://example.test/google-avatar.png'},
        )
        image_data = BytesIO()
        Image.new('RGB', (2, 2), color='orange').save(image_data, format='PNG')
        image_bytes = image_data.getvalue()
        self.client.force_login(user)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('webapp:account_settings'),
                {
                    'first_name': 'Custom',
                    'last_name': '',
                    'phone_number': '',
                    'avatar': SimpleUploadedFile(
                        'profile.png',
                        image_bytes,
                        content_type='image/png',
                    ),
                },
            )

            self.assertRedirects(
                response,
                reverse('webapp:account_settings'),
                fetch_redirect_response=False,
            )
            user.profile.refresh_from_db()
            self.assertTrue(user.profile.avatar.name.startswith('profiles/'))
            settings_response = self.client.get(reverse('webapp:account_settings'))
            self.assertContains(settings_response, user.profile.avatar.url)
            self.assertNotContains(
                settings_response,
                'src="https://example.test/google-avatar.png"',
            )
            navbar_response = self.client.get(reverse('webapp:home'))
            self.assertContains(navbar_response, user.profile.avatar.url)
            self.assertNotContains(navbar_response, 'google-avatar.png')

    def test_invalid_profile_photo_is_rejected(self):
        user = User.objects.create_user(
            username='bad-avatar@example.com',
            email='bad-avatar@example.com',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('webapp:account_settings'),
            {
                'first_name': '',
                'last_name': '',
                'phone_number': '',
                'avatar': SimpleUploadedFile(
                    'not-an-image.txt',
                    b'this is not an image',
                    content_type='text/plain',
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upload a valid image.')
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.avatar)

    def test_clearing_uploaded_photo_returns_to_google_avatar_and_removes_file(self):
        user = User.objects.create_user(
            username='clear-avatar@example.com',
            email='clear-avatar@example.com',
        )
        SocialAccount.objects.create(
            user=user,
            provider='google',
            uid='google-clear-avatar',
            extra_data={'picture': 'https://example.test/google-avatar.png'},
        )
        image_data = BytesIO()
        Image.new('RGB', (2, 2), color='orange').save(image_data, format='PNG')
        image_bytes = image_data.getvalue()
        self.client.force_login(user)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            user.profile.avatar.save(
                'profile.png',
                SimpleUploadedFile(
                    'profile.png',
                    image_bytes,
                    content_type='image/png',
                ),
            )
            previous_avatar_path = user.profile.avatar.path
            response = self.client.post(
                reverse('webapp:account_settings'),
                {
                    'clear_avatar': 'on',
                    'first_name': '',
                    'last_name': '',
                    'phone_number': '',
                },
            )

            self.assertRedirects(
                response,
                reverse('webapp:account_settings'),
                fetch_redirect_response=False,
            )
            user.profile.refresh_from_db()
            self.assertFalse(user.profile.avatar)
            self.assertFalse(os.path.exists(previous_avatar_path))
            settings_response = self.client.get(reverse('webapp:account_settings'))
            self.assertContains(settings_response, 'google-avatar.png')

    def test_account_settings_requires_login_and_displays_profile(self):
        settings_url = reverse('webapp:account_settings')
        response = self.client.get(settings_url)

        self.assertRedirects(response, f"{reverse('webapp:sign_in')}?next={settings_url}")

        user = User.objects.create_user(
            username='settings@example.com',
            email='settings@example.com',
            first_name='Alex',
            last_name='Buyer',
        )
        self.client.force_login(user)
        response = self.client.get(settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account-settings.html')
        self.assertContains(response, 'value="Alex"')
        self.assertContains(response, 'value="Buyer"')
        self.assertContains(response, 'settings@example.com')
        self.assertContains(response, 'Email is tied to your Google login.')
        self.assertContains(response, 'Delete account')
        self.assertContains(response, 'Type DELETE to confirm')
        self.assertContains(response, 'js/account-settings.js')
        self.assertContains(response, 'Quick links')
        self.assertContains(response, 'Help &amp; legal')
        self.assertContains(response, 'Privacy Policy')
        self.assertContains(response, 'bolgarage123@gmail.com')
        self.assertContains(response, '09365241396')
        self.assertContains(response, 'data-avatar-input')
        self.assertContains(response, 'settings-avatar-camera')
        self.assertNotContains(response, 'Choose File')

    def test_new_user_automatically_gets_profile(self):
        user = User.objects.create_user(
            username='profile@example.com',
            email='profile@example.com',
            phone='09123456789',
        )

        profile = Profile.objects.get(user=user)

        self.assertEqual(profile.phone_number, '09123456789')

    def test_profile_settings_updates_user_and_profile_phone(self):
        user = User.objects.create_user(
            username='edit-profile@example.com',
            email='edit-profile@example.com',
            first_name='Old',
            last_name='Name',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('webapp:account_settings'),
            {
                'first_name': 'New',
                'last_name': 'Name',
                'phone_number': '+63 (912) 345-6789',
            },
        )

        self.assertRedirects(
            response,
            reverse('webapp:account_settings'),
            fetch_redirect_response=False,
        )
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.last_name), ('New', 'Name'))
        self.assertEqual(user.phone, '+63 (912) 345-6789')
        self.assertEqual(user.profile.phone_number, '+63 (912) 345-6789')
        self.assertContains(self.client.get(reverse('webapp:account_settings')), 'Your profile has been updated.')

    def test_profile_settings_rejects_invalid_phone_number(self):
        user = User.objects.create_user(
            username='invalid-phone@example.com',
            email='invalid-phone@example.com',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('webapp:account_settings'),
            {
                'first_name': 'Buyer',
                'last_name': '',
                'phone_number': 'abc123',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Use only digits, spaces, +, -, and parentheses.')
        self.assertContains(response, 'aria-invalid="true"')
        user.refresh_from_db()
        self.assertEqual(user.first_name, '')
        self.assertEqual(user.profile.phone_number, '')

    def test_delete_account_requires_exact_confirmation_and_post(self):
        user = User.objects.create_user(
            username='delete-me@example.com',
            email='delete-me@example.com',
        )
        self.client.force_login(user)
        delete_url = reverse('webapp:account_delete')

        self.assertEqual(self.client.get(delete_url).status_code, 405)
        response = self.client.post(delete_url, {'confirmation': 'delete'})

        self.assertRedirects(
            response,
            reverse('webapp:account_settings'),
            fetch_redirect_response=False,
        )
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        self.assertContains(self.client.get(reverse('webapp:account_settings')), 'Type DELETE exactly')

    def test_delete_account_removes_profile_and_social_account(self):
        user = User.objects.create_user(
            username='delete-social@example.com',
            email='delete-social@example.com',
        )
        profile = user.profile
        social_account = SocialAccount.objects.create(
            user=user,
            provider='google',
            uid='delete-google-account',
            extra_data={},
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('webapp:account_delete'),
            {'confirmation': 'DELETE'},
        )

        self.assertRedirects(
            response,
            reverse('webapp:home'),
            fetch_redirect_response=False,
        )
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertFalse(Profile.objects.filter(pk=profile.pk).exists())
        self.assertFalse(SocialAccount.objects.filter(pk=social_account.pk).exists())
        self.assertContains(self.client.get(reverse('webapp:home')), 'Your account has been deleted.')

    def test_help_and_legal_pages_load(self):
        pages = [
            ('faqs', 'faqs.html', 'Frequently Asked Questions', None),
            ('terms', 'terms.html', 'Terms &amp; Conditions', 'Effective date: November 2026'),
            ('privacy', 'privacy.html', 'Privacy Policy', 'Effective date: October 2026'),
        ]
        for route, template, heading, effective_date in pages:
            with self.subTest(page=route):
                response = self.client.get(reverse(f'webapp:{route}'))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)
                self.assertContains(response, heading)
                if effective_date:
                    self.assertContains(response, effective_date)
                    self.assertNotContains(response, 'Effective date: October 26, 2026')

    def test_faqs_use_confirmed_business_policies(self):
        response = self.client.get(reverse('webapp:faqs'))

        self.assertContains(response, 'at least ₱5,000')
        self.assertContains(response, 'Monday–Friday, 9:00 AM–8:00 PM')
        self.assertContains(response, 'Saturday–Sunday, 9:00 AM–5:00 PM')
        self.assertContains(response, 'Cash, bank transfer, and GCash')
        self.assertNotContains(response, '[__ days]')

    def test_contact_page_loads_as_a_separate_page(self):
        response = self.client.get(reverse('webapp:contact'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'contact.html')
        self.assertContains(response, 'Send us a message')
        self.assertContains(response, 'contact-form-card')
        self.assertContains(response, 'bolgarage123@gmail.com')
        self.assertContains(response, 'Holiday Homes, Biclatan, General Trias, Cavite')
        self.assertContains(response, 'class="active" aria-current="page">Contact</a>')
        self.assertContains(response, '09365241396')
        self.assertContains(response, 'https://www.facebook.com/kuyabolcute/')
        self.assertContains(response, 'Monday–Friday')
        self.assertContains(response, '9:00 AM–8:00 PM')
        self.assertContains(response, 'Saturday–Sunday')
        self.assertContains(response, '9:00 AM–5:00 PM')
        self.assertContains(response, 'maps.google.com/maps')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    @override_settings(
        SMTP_USERNAME='bolgarage123@gmail.com',
        SMTP_PASSWORD='test-app-password',
        DEFAULT_FROM_EMAIL='bolgarage123@gmail.com',
        EMAIL_SENDER_NAME='BOL Garage',
        CONTACT_NOTIFICATION_EMAIL='bolgarage123@gmail.com',
    )
    def test_contact_form_saves_message_sends_admin_email_and_confirms_submission(self):
        response = self.client.post(
            reverse('webapp:contact'),
            {
                'name': 'Jamie Buyer',
                'phone': '09123456789',
                'email': 'jamie@example.com',
                'topic': 'selling',
                'message': 'I would like to sell my vehicle.',
            },
        )

        self.assertRedirects(response, reverse('webapp:contact'), fetch_redirect_response=False)
        contact_message = ContactMessage.objects.get()
        self.assertEqual(contact_message.name, 'Jamie Buyer')
        self.assertEqual(contact_message.topic, 'selling')
        self.assertEqual(contact_message.email, 'jamie@example.com')
        self.assertEqual(contact_message.message, 'I would like to sell my vehicle.')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['bolgarage123@gmail.com'])
        self.assertEqual(mail.outbox[0].from_email, 'BOL Garage <bolgarage123@gmail.com>')
        self.assertIn('Selling my vehicle', mail.outbox[0].subject)
        self.assertIn('I would like to sell my vehicle.', mail.outbox[0].body)
        html_body, html_mimetype = mail.outbox[0].alternatives[0]
        self.assertEqual(html_mimetype, 'text/html')
        self.assertIn('cid:bol-garage-logo', html_body)
        self.assertIn('BOL GARAGE', html_body)
        self.assertIn('Jamie Buyer', html_body)
        self.assertTrue(
            any(
                attachment['Content-ID'] == '<bol-garage-logo>'
                and attachment.get_content_disposition() == 'inline'
                for attachment in mail.outbox[0].attachments
                if isinstance(attachment, MIMEPart)
            )
        )
        self.assertIn(
            f'/garage/contact-messages/?message={contact_message.pk}',
            mail.outbox[0].body,
        )
        self.assertContains(self.client.get(reverse('webapp:contact')), 'Your message has been sent to Bol Garage.')

    @override_settings(SMTP_USERNAME='', SMTP_PASSWORD='')
    def test_contact_message_is_saved_when_email_alert_is_not_configured(self):
        response = self.client.post(
            reverse('webapp:contact'),
            {
                'name': 'Jamie Buyer',
                'phone': '09123456789',
                'email': '',
                'topic': 'selling',
                'message': 'I would like to sell my vehicle.',
            },
            follow=True,
        )

        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertContains(response, 'Your message was saved, but the email alert could not be sent.')
        self.assertEqual(mail.outbox, [])

    def test_contact_form_rejects_invalid_submission(self):
        response = self.client.post(
            reverse('webapp:contact'),
            {
                'name': '',
                'phone': '09123456789',
                'email': 'not-an-email',
                'topic': 'unknown',
                'message': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required.')
        self.assertContains(response, 'Enter a valid email address.')
        self.assertContains(response, 'Select a valid choice.')
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_staff_can_view_contact_messages_in_garage_page(self):
        contact_message = ContactMessage.objects.create(
            name='Jamie Buyer',
            phone='09123456789',
            email='jamie@example.com',
            topic='selling',
            message='I would like to sell my vehicle.',
        )
        staff_user = User.objects.create_superuser(
            username='contact-admin@example.com',
            email='contact-admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('webapp:contact_messages'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'contact-messages.html')
        self.assertContains(response, 'Contact messages')
        self.assertContains(response, 'Jamie Buyer')
        self.assertContains(response, 'Selling my vehicle')
        self.assertContains(response, 'I would like to sell my vehicle.')
        self.assertContains(response, 'https://mail.google.com/mail/')
        self.assertContains(response, 'jamie@example.com')
        compose_params = parse_qs(urlparse(response.context['reply_compose_url']).query)
        self.assertEqual(compose_params['to'], ['jamie@example.com'])
        self.assertEqual(compose_params['view'], ['cm'])
        self.assertEqual(
            compose_params['su'],
            ['Following up on your selling my vehicle message'],
        )
        self.assertIn('Hi Jamie Buyer', compose_params['body'][0])
        self.assertContains(response, '09123456789')
        self.assertNotContains(response, 'href="tel:09123456789"')
        self.assertNotContains(response, 'Call Jamie Buyer')
        self.assertContains(response, 'class="inbox"')
        self.assertContains(response, reverse('webapp:contact_messages'))
        self.assertContains(response, 'All (1)')
        self.assertContains(response, 'Selling my vehicle (1)')
        self.assertContains(response, 'Question about a car (0)')
        self.assertContains(response, 'Plan a visit (0)')
        self.assertContains(response, 'Other (0)')
        self.assertContains(response, reverse('webapp:contact_message_delete', args=[contact_message.pk]))
        self.assertContains(response, 'Delete message')
        self.assertContains(response, 'data-confirmation-form')
        self.assertEqual(response.context['selected_message'].pk, contact_message.pk)

    def test_staff_can_delete_contact_message_and_preserve_topic_filter(self):
        contact_message = ContactMessage.objects.create(
            name='Jamie Buyer',
            phone='09123456789',
            topic='selling',
            message='Please remove this message.',
        )
        staff_user = User.objects.create_superuser(
            username='contact-delete-admin@example.com',
            email='contact-delete-admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:contact_message_delete', args=[contact_message.pk]),
            {'topic': 'selling'},
            follow=True,
        )

        self.assertRedirects(
            response,
            f"{reverse('webapp:contact_messages')}?topic=selling",
        )
        self.assertFalse(ContactMessage.objects.filter(pk=contact_message.pk).exists())
        self.assertContains(response, 'Contact message permanently deleted.')

    def test_contact_message_delete_requires_post_and_staff_access(self):
        contact_message = ContactMessage.objects.create(
            name='Jamie Buyer',
            phone='09123456789',
            topic='selling',
            message='Please keep this message.',
        )
        staff_user = User.objects.create_superuser(
            username='contact-delete-method-admin@example.com',
            email='contact-delete-method-admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:contact_message_delete', args=[contact_message.pk]),
        )
        self.assertEqual(response.status_code, 405)
        self.assertTrue(ContactMessage.objects.filter(pk=contact_message.pk).exists())

        buyer = User.objects.create_user(
            username='contact-delete-buyer@example.com',
            email='contact-delete-buyer@example.com',
        )
        self.client.force_login(buyer)
        response = self.client.post(
            reverse('webapp:contact_message_delete', args=[contact_message.pk]),
        )
        self.assertRedirects(response, reverse('webapp:home'))
        self.assertTrue(ContactMessage.objects.filter(pk=contact_message.pk).exists())

    def test_contact_message_category_tabs_filter_messages_and_keep_selection(self):
        selling_message = ContactMessage.objects.create(
            name='Seller',
            phone='09123456789',
            topic='selling',
            message='Selling details.',
        )
        visit_message = ContactMessage.objects.create(
            name='Visitor',
            phone='09123456789',
            topic='visit',
            message='Visit details.',
        )
        staff_user = User.objects.create_superuser(
            username='contact-filter-admin@example.com',
            email='contact-filter-admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:contact_messages'),
            {'topic': 'selling', 'message': selling_message.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="is-active" aria-current="page">Selling my vehicle (1)</a>')
        self.assertContains(response, 'Seller')
        self.assertNotContains(response, 'Visitor')
        self.assertContains(response, f'?topic=selling&amp;message={selling_message.pk}')
        self.assertEqual(response.context['selected_message'].pk, selling_message.pk)
        self.assertEqual(response.context['total_messages'], 2)

    def test_contact_message_list_scrolls_at_five_messages(self):
        for index in range(5):
            ContactMessage.objects.create(
                name=f'Contact {index}',
                phone='09123456789',
                topic='selling',
                message=f'Message {index}',
            )
        staff_user = User.objects.create_superuser(
            username='contact-scroll-admin@example.com',
            email='contact-scroll-admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('webapp:contact_messages'))

        self.assertContains(response, 'class="inbox inbox-scrollable"')

    def test_buyer_cannot_access_contact_messages_page(self):
        buyer = User.objects.create_user(
            username='contact-buyer@example.com',
            email='contact-buyer@example.com',
        )
        self.client.force_login(buyer)

        response = self.client.get(reverse('webapp:contact_messages'))

        self.assertRedirects(response, reverse('webapp:home'))

    def test_recently_sold_car_shows_uploaded_photo(self):
        self.car.status = 'sold'
        self.car.save()
        CarPhoto.objects.create(car=self.car, image='cars/sold-vios.jpg')

        response = self.client.get(reverse('webapp:home'))

        self.assertContains(response, 'class="photo sold-card-photo"')
        self.assertContains(response, 'src="/media/cars/sold-vios.jpg"')

    def test_car_card_shows_carousel_controls_for_multiple_photos(self):
        CarPhoto.objects.create(car=self.car, image='cars/vios-exterior.jpg', order=0)
        CarPhoto.objects.create(car=self.car, image='cars/vios-interior.jpg', order=1)

        response = self.client.get(reverse('webapp:home'))

        self.assertContains(response, 'data-card-carousel')
        self.assertContains(response, 'Previous photo')
        self.assertContains(response, 'Next photo')
        self.assertContains(response, '1 / 2')
        self.assertContains(response, 'cars/vios-exterior.jpg')
        self.assertContains(response, 'cars/vios-interior.jpg')

    def test_car_list_page_loads(self):
        response = self.client.get(reverse('webapp:car_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Toyota Vios')
        self.assertContains(response, 'class="active" aria-current="page">Available cars</a>')
        self.assertNotContains(response, 'data-inquiry-status-open')

    def test_buyer_can_view_only_their_open_inquiry_statuses_on_car_list(self):
        buyer = User.objects.create_user(
            username='inquiry-status@example.com',
            email='inquiry-status@example.com',
        )
        other_buyer = User.objects.create_user(
            username='other-inquiry@example.com',
            email='other-inquiry@example.com',
        )
        Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='Is it still available?',
        )
        Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='reserve',
            message='I would like to reserve it.',
            status='contacted',
        )
        Inquiry.objects.create(
            car=self.car,
            buyer=other_buyer,
            kind='inquiry',
            message='This belongs to another buyer.',
        )
        Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='This inquiry is closed.',
            status='closed',
        )
        Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='This inquiry was cancelled.',
            status='cancelled',
        )
        self.client.force_login(buyer)

        response = self.client.get(reverse('webapp:car_list'))

        self.assertContains(response, 'data-inquiry-status-open')
        self.assertContains(response, 'Contacted')
        self.assertContains(response, 'Pending')
        self.assertContains(response, '2 open inquiries')
        self.assertContains(response, 'Only open inquiries are shown.')
        self.assertContains(response, 'Contacted means the garage has replied to you by email.')
        self.assertContains(response, 'Cancel inquiry')
        self.assertContains(response, 'class="inquiry-status-item-actions"')
        self.assertContains(response, 'class="inquiry-cancel-button"')
        self.assertNotContains(response, 'class="btn inquiry-cancel-button"')
        self.assertNotContains(response, 'This inquiry was cancelled.')
        self.assertEqual(response.context['user_inquiries'].count(), 2)

    def test_buyer_can_cancel_their_open_inquiry(self):
        buyer = User.objects.create_user(
            username='cancel-inquiry@example.com',
            email='cancel-inquiry@example.com',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='reserve',
            message='I would like to reserve it.',
        )
        self.client.force_login(buyer)

        page = self.client.get(reverse('webapp:car_list'))
        self.assertContains(page, reverse('webapp:cancel_inquiry', args=[inquiry.pk]))
        self.assertContains(page, 'data-confirmation-form')
        self.assertContains(page, 'id="confirmation-dialog"')

        response = self.client.post(
            reverse('webapp:cancel_inquiry', args=[inquiry.pk]),
            {'next': reverse('webapp:car_list')},
            follow=True,
        )

        self.assertRedirects(response, reverse('webapp:car_list'))
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.status, 'cancelled')
        self.assertContains(response, 'Your inquiry has been cancelled.')
        self.assertEqual(response.context['user_inquiries'].count(), 0)

    def test_buyer_cannot_cancel_another_buyers_or_closed_inquiry(self):
        buyer = User.objects.create_user(
            username='cancel-owner@example.com',
            email='cancel-owner@example.com',
        )
        other_buyer = User.objects.create_user(
            username='cancel-other@example.com',
            email='cancel-other@example.com',
        )
        owned_inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            message='Owned inquiry.',
        )
        other_inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=other_buyer,
            message='Another buyer inquiry.',
        )
        closed_inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            message='Already closed.',
            status='closed',
        )
        self.client.force_login(buyer)

        response = self.client.post(
            reverse('webapp:cancel_inquiry', args=[other_inquiry.pk]),
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse('webapp:cancel_inquiry', args=[closed_inquiry.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Inquiry.objects.filter(pk=owned_inquiry.pk, status='new').exists())
        self.assertTrue(Inquiry.objects.filter(pk=other_inquiry.pk, status='new').exists())
        self.assertTrue(Inquiry.objects.filter(pk=closed_inquiry.pk, status='closed').exists())

    def test_cancel_inquiry_requires_post(self):
        buyer = User.objects.create_user(
            username='cancel-method@example.com',
            email='cancel-method@example.com',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            message='Keep this inquiry.',
        )
        self.client.force_login(buyer)

        response = self.client.get(reverse('webapp:cancel_inquiry', args=[inquiry.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Inquiry.objects.filter(pk=inquiry.pk, status='new').exists())

    def test_buyer_inquiry_status_button_is_available_on_other_customer_pages(self):
        buyer = User.objects.create_user(
            username='customer-page@example.com',
            email='customer-page@example.com',
        )
        Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='Is it still available?',
        )
        self.client.force_login(buyer)

        response = self.client.get(reverse('webapp:home'))

        self.assertContains(response, 'data-inquiry-status-open')
        self.assertContains(response, 'data-inquiry-status-dialog')
        self.assertContains(response, 'Toyota Vios')

    def test_admin_does_not_see_buyer_inquiry_status_modal_on_car_list(self):
        admin = User.objects.create_user(
            username='inquiry-admin@example.com',
            email='inquiry-admin@example.com',
            role='admin',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('webapp:car_list'))

        self.assertNotContains(response, 'data-inquiry-status-open')
        self.assertNotContains(response, 'data-inquiry-status-dialog')

    def test_car_list_filters_from_database(self):
        other_car = Car.objects.create(
            brand='Honda',
            model='Civic',
            year=2017,
            transmission='manual',
            fuel='gasoline',
            mileage=71000,
            asking_price=598000,
            status='available',
        )

        response = self.client.get(reverse('webapp:car_list'), {'brand': 'Toyota'})

        self.assertContains(response, 'Toyota Vios')
        self.assertNotContains(response, 'Honda Civic')
        self.assertEqual(Car.objects.filter(pk=other_car.pk).count(), 1)

    def test_car_list_shows_four_cars_per_page_and_preserves_filters(self):
        cars = [
            Car.objects.create(
                brand='Toyota',
                model=f'Model {index}',
                year=2020,
                transmission='automatic',
                fuel='gasoline',
                mileage=10000 + index,
                asking_price=500000 + index,
                status='available',
            )
            for index in range(1, 5)
        ]

        filters = {'brand': 'Toyota', 'sort': 'price-low'}
        first_page = self.client.get(reverse('webapp:car_list'), filters)
        second_page = self.client.get(reverse('webapp:car_list'), {**filters, 'page': 2})

        self.assertContains(first_page, 'Showing 1–4 of 5 cars')
        self.assertContains(first_page, 'Page 1 of 2')
        self.assertContains(first_page, 'Toyota Vios')
        self.assertContains(first_page, cars[2].model)
        self.assertNotContains(first_page, 'Model 4')
        self.assertContains(first_page, 'brand=Toyota&amp;sort=price-low&amp;page=2')

        self.assertContains(second_page, 'Showing 5–5 of 5 cars')
        self.assertContains(second_page, 'Page 2 of 2')
        self.assertContains(second_page, 'Model 4')
        self.assertNotContains(second_page, 'Toyota Vios')
        self.assertContains(second_page, 'brand=Toyota&amp;sort=price-low&amp;page=1')

    def test_car_detail_page_shows_database_car(self):
        response = self.client.get(reverse('webapp:car_detail', args=[self.car.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Well maintained.')
        self.assertContains(response, 'Interested in this car?')

    def test_non_public_car_detail_is_not_found(self):
        self.car.status = 'sold'
        self.car.save()

        response = self.client.get(reverse('webapp:car_detail', args=[self.car.pk]))

        self.assertEqual(response.status_code, 404)

    def test_sign_in_page_loads(self):
        response = self.client.get(reverse('webapp:sign_in'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your account')
        self.assertTemplateUsed(response, 'signin.html')
        self.assertContains(response, 'data-password-toggle', count=3)
        self.assertContains(response, 'aria-label="Show password"', count=3)
        self.assertContains(response, 'js/signin.js?v=3')
        self.assertContains(response, 'placeholder="e.g. name@example.com"')
        self.assertContains(response, 'placeholder="Enter your password"')
        self.assertContains(response, 'href="/accounts/password/reset/">Forgot password?</a>')
        self.assertContains(response, 'placeholder="e.g. Juan Dela Cruz"')
        self.assertContains(response, 'placeholder="e.g. 09123456789"')
        self.assertContains(response, 'placeholder="Create a password"')
        self.assertContains(response, 'placeholder="Re-enter your password"')
        self.assertContains(response, 'class="auth-divider"><span>or</span>')
        self.assertContains(response, 'Continue with Google')
        self.assertContains(response, 'href="/accounts/google/login/"')
        self.assertContains(response, 'class="google-signin-icon"')
        self.assertContains(response, 'fill="#4285F4"')

    def test_password_reset_page_uses_site_layout(self):
        response = self.client.get(reverse('account_reset_password'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/password_reset.html')
        self.assertContains(response, 'href="/static/css/styles.css?v=12"')
        self.assertContains(response, 'Forgot your password?')
        self.assertContains(response, 'Send reset link')
        self.assertNotContains(response, 'Menu:')

    def test_password_reset_done_page_uses_site_layout(self):
        response = self.client.get(reverse('account_reset_password_done'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/password_reset_done.html')
        self.assertContains(response, 'Check your email')
        self.assertNotContains(response, 'Menu:')

    def test_inactive_account_page_uses_site_layout_and_explains_reactivation(self):
        response = self.client.get(reverse('account_inactive'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/account_inactive.html')
        self.assertContains(response, 'Only a Bol Garage admin can reactivate an account.')
        self.assertContains(response, reverse('webapp:contact'))
        self.assertNotContains(response, 'Menu:')

    def test_invalid_password_reset_link_uses_site_layout(self):
        response = self.client.get(
            reverse(
                'account_reset_password_from_key',
                kwargs={'uidb36': '1', 'key': 'invalid'},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/password_reset_from_key.html')
        self.assertContains(response, 'Reset link expired')
        self.assertNotContains(response, 'Menu:')

    def test_password_reset_email_uses_branded_notification_template(self):
        user = User.objects.create_user(
            username='reset@example.com',
            email='reset@example.com',
            password='SolidPassword2026!',
        )

        response = self.client.post(
            reverse('account_reset_password'),
            {'email': user.email},
        )

        self.assertRedirects(
            response,
            reverse('account_reset_password_done'),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        reset_email = mail.outbox[0]
        self.assertIn('BOL Garage password reset', reset_email.subject)
        self.assertEqual(reset_email.to, [user.email])
        self.assertIn('BOL GARAGE', reset_email.body)
        self.assertIn('/accounts/password/reset/key/', reset_email.body)
        html_body, html_mimetype = reset_email.alternatives[0]
        self.assertEqual(html_mimetype, 'text/html')
        self.assertIn('cid:bol-garage-logo', html_body)
        self.assertIn('Reset your password', html_body)
        self.assertIn('background-color:#f4f2ed', html_body)
        self.assertIn('margin:0 0 24px;text-align:center;', html_body)
        self.assertIn('/accounts/password/reset/key/', html_body)
        self.assertTrue(
            any(
                attachment['Content-ID'] == '<bol-garage-logo>'
                and attachment.get_content_disposition() == 'inline'
                for attachment in reset_email.attachments
                if isinstance(attachment, MIMEPart)
            )
        )
    def test_password_reset_form_has_show_hide_controls(self):
        user = User.objects.create_user(
            username='show-password@example.com',
            email='show-password@example.com',
            password='SolidPassword2026!',
        )
        self.client.post(
            reverse('account_reset_password'),
            {'email': user.email},
        )
        reset_url = next(
            line for line in mail.outbox[0].body.splitlines()
            if line.startswith('http')
        )
        reset_path = urlparse(reset_url).path

        response = self.client.get(reset_path, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/password_reset_from_key.html')
        self.assertContains(response, 'data-password-toggle', count=2)
        self.assertContains(response, 'aria-label="Show password"', count=2)
        self.assertContains(response, 'js/password-toggle.js')

    def test_legacy_sign_in_url_redirects_to_sign_in_page(self):
        response = self.client.get('/cars/signin.html')

        self.assertRedirects(response, '/signin/')

    @override_settings(
        SMTP_USERNAME='bolgarage123@gmail.com',
        SMTP_PASSWORD='test-app-password',
        DEFAULT_FROM_EMAIL='bolgarage123@gmail.com',
        EMAIL_SENDER_NAME='BOL Garage',
        CONTACT_NOTIFICATION_EMAIL='bolgarage123@gmail.com',
    )
    def test_signup_creates_account_sends_welcome_email_and_signs_user_in(self):
        response = self.client.post(
            reverse('webapp:sign_up'),
            {
                'full_name': 'Jamie Buyer',
                'email': 'jamie@example.com',
                'phone': '09123456789',
                'password1': 'SolidPassword2026!',
                'password2': 'SolidPassword2026!',
            },
        )

        self.assertRedirects(response, reverse('webapp:home'))
        user = User.objects.get(email='jamie@example.com')
        self.assertEqual(user.get_full_name(), 'Jamie Buyer')
        self.assertTrue(user.check_password('SolidPassword2026!'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.assertEqual(len(mail.outbox), 1)
        welcome_email = mail.outbox[0]
        self.assertEqual(welcome_email.subject, 'Welcome to BOL Garage')
        self.assertEqual(welcome_email.to, [user.email])
        self.assertIn('Welcome to BOL Garage', welcome_email.body)
        html_body, html_mimetype = welcome_email.alternatives[0]
        self.assertEqual(html_mimetype, 'text/html')
        self.assertIn('Welcome to BOL Garage, Jamie!', html_body)
        self.assertIn('cid:bol-garage-logo', html_body)
        self.assertTrue(
            any(
                attachment['Content-ID'] == '<bol-garage-logo>'
                and attachment.get_content_disposition() == 'inline'
                for attachment in welcome_email.attachments
                if isinstance(attachment, MIMEPart)
            )
        )

        self.client.logout()
        duplicate_response = self.client.post(
            reverse('webapp:sign_up'),
            {
                'full_name': 'Jamie Buyer',
                'email': user.email,
                'phone': '09123456789',
                'password1': 'SolidPassword2026!',
                'password2': 'SolidPassword2026!',
            },
        )
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertContains(duplicate_response, 'An account with this email already exists.')
        self.assertEqual(User.objects.filter(email__iexact=user.email).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        SMTP_USERNAME='bolgarage123@gmail.com',
        SMTP_PASSWORD='test-app-password',
        DEFAULT_FROM_EMAIL='bolgarage123@gmail.com',
        EMAIL_SENDER_NAME='BOL Garage',
        CONTACT_NOTIFICATION_EMAIL='bolgarage123@gmail.com',
    )
    def test_inactivity_command_sends_warnings_once_and_deactivates_at_120_days(self):
        now = timezone.now()
        user_60 = User.objects.create_user(
            username='inactive-60@example.com',
            email='inactive-60@example.com',
        )
        anchor_60 = now - timedelta(days=60)
        User.objects.filter(pk=user_60.pk).update(
            date_joined=anchor_60,
            inactivity_reset_at=anchor_60,
        )
        user_90 = User.objects.create_user(
            username='inactive-90@example.com',
            email='inactive-90@example.com',
        )
        anchor_90 = now - timedelta(days=90)
        User.objects.filter(pk=user_90.pk).update(
            date_joined=anchor_90,
            inactivity_reset_at=anchor_90,
        )
        overdue_user = User.objects.create_user(
            username='inactive-120@example.com',
            email='inactive-120@example.com',
        )
        anchor_120 = now - timedelta(days=120)
        User.objects.filter(pk=overdue_user.pk).update(
            date_joined=anchor_120,
            inactivity_reset_at=anchor_120,
        )
        staff_user = User.objects.create_user(
            username='inactive-staff@example.com',
            email='inactive-staff@example.com',
            role='admin',
            is_staff=True,
        )
        old_anchor = now - timedelta(days=150)
        User.objects.filter(pk=staff_user.pk).update(
            date_joined=old_anchor,
            inactivity_reset_at=old_anchor,
        )

        call_command('process_account_inactivity')

        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('60 days', mail.outbox[0].subject)
        self.assertIn('90 days', mail.outbox[1].subject)
        self.assertIn('/signin/', mail.outbox[0].alternatives[0][0])
        user_60.refresh_from_db()
        user_90.refresh_from_db()
        overdue_user.refresh_from_db()
        staff_user.refresh_from_db()
        self.assertEqual(user_60.inactivity_warning_60_sent_for, anchor_60)
        self.assertEqual(user_90.inactivity_warning_60_sent_for, anchor_90)
        self.assertEqual(user_90.inactivity_warning_90_sent_for, anchor_90)
        self.assertFalse(overdue_user.is_active)
        self.assertTrue(staff_user.is_active)

        call_command('process_account_inactivity')
        self.assertEqual(len(mail.outbox), 2)

        last_login = timezone.now()
        User.objects.filter(pk=user_60.pk).update(last_login=last_login)
        with patch(
            'webapp.management.commands.process_account_inactivity.timezone.now',
            return_value=last_login + timedelta(days=61),
        ):
            call_command('process_account_inactivity')
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn('60 days', mail.outbox[2].subject)

    def test_signin_authenticates_with_email(self):
        user = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )

        response = self.client.post(
            reverse('webapp:sign_in'),
            {'username': 'buyer@example.com', 'password': 'SolidPassword2026!'},
        )

        self.assertRedirects(response, reverse('webapp:home'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_google_verified_email_prefers_matching_staff_account(self):
        buyer = User.objects.create_user(
            username='google-buyer@example.com',
            email='google-buyer@example.com',
        )
        EmailAddress.objects.create(
            user=buyer,
            email=buyer.email,
            verified=True,
            primary=True,
        )
        admin = User.objects.create_superuser(
            username='google-admin@example.com',
            email=buyer.email,
            password='SolidPassword2026!',
        )
        provider = GoogleProvider(request=None, app=SimpleNamespace(settings={}))
        sociallogin = SocialLogin(
            user=User(),
            account=SocialAccount(provider='google', uid='new-google-identity'),
            email_addresses=[
                EmailAddress(email=buyer.email, verified=True, primary=True),
            ],
            provider=provider,
        )

        result = GarageSocialAccountAdapter().authenticate_by_email(sociallogin)

        self.assertIsNotNone(result)
        self.assertEqual(result[0], admin)
        self.assertTrue(settings.SOCIALACCOUNT_AUTO_SIGNUP)
        self.assertEqual(settings.LOGIN_REDIRECT_URL, '/')

    def test_google_login_moves_existing_link_to_matching_staff_account(self):
        buyer = User.objects.create_user(
            username='google-buyer@example.com',
            email='google-buyer@example.com',
        )
        admin = User.objects.create_superuser(
            username='google-admin@example.com',
            email=buyer.email,
            password='SolidPassword2026!',
        )
        linked_account = SocialAccount.objects.create(
            user=buyer,
            provider='google',
            uid='linked-google-identity',
            extra_data={},
        )
        provider = GoogleProvider(
            request=None,
            app=SimpleNamespace(settings={}),
        )
        sociallogin = SocialLogin(
            user=buyer,
            account=linked_account,
            email_addresses=[
                EmailAddress(email=buyer.email, verified=True, primary=True),
            ],
            provider=provider,
        )

        GarageSocialAccountAdapter().pre_social_login(
            RequestFactory().get('/'),
            sociallogin,
        )

        linked_account.refresh_from_db()
        self.assertEqual(linked_account.user, admin)
        self.assertEqual(sociallogin.user, admin)

    def test_allauth_redirects_staff_to_dashboard_and_buyers_home(self):
        staff_user = User(is_staff=True)
        buyer = User(is_staff=False)
        adapter = GarageAccountAdapter()

        self.assertEqual(
            adapter.get_login_redirect_url(SimpleNamespace(user=staff_user)),
            reverse('webapp:dashboard'),
        )
        self.assertEqual(
            adapter.get_login_redirect_url(SimpleNamespace(user=buyer)),
            '/',
        )

    @override_settings(
        SMTP_USERNAME='bolgarage123@gmail.com',
        SMTP_PASSWORD='test-app-password',
        DEFAULT_FROM_EMAIL='bolgarage123@gmail.com',
        EMAIL_SENDER_NAME='BOL Garage',
        CONTACT_NOTIFICATION_EMAIL='bolgarage123@gmail.com',
    )
    def test_google_new_account_is_created_sends_welcome_email_and_redirected_home(self):
        request = RequestFactory().get('/', HTTP_HOST='testserver')
        request.user = AnonymousUser()
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        provider = GoogleProvider(request=request, app=SimpleNamespace(settings={}))
        email = 'new-google-buyer@example.com'
        sociallogin = SocialLogin(
            user=User(email=email, first_name='Google', last_name='Buyer'),
            account=SocialAccount(provider='google', uid='new-google-signup'),
            email_addresses=[
                EmailAddress(email=email, verified=True, primary=True),
            ],
            provider=provider,
        )

        with request_context(request):
            response = process_signup(request, sociallogin)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')
        user = User.objects.get(email=email)
        self.assertEqual(user.get_full_name(), 'Google Buyer')
        self.assertEqual(user.role, 'buyer')
        self.assertFalse(user.has_usable_password())
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [email])
        self.assertEqual(mail.outbox[0].subject, 'Welcome to BOL Garage')
        self.assertIn('Welcome to BOL Garage, Google!', mail.outbox[0].alternatives[0][0])

    def test_admin_signin_redirects_to_admin_dashboard(self):
        admin_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )

        response = self.client.post(
            reverse('webapp:sign_in'),
            {'username': 'admin@example.com', 'password': 'SolidPassword2026!'},
            follow=True,
        )

        self.assertEqual(
            response.redirect_chain,
            [(reverse('webapp:dashboard'), 302)],
        )
        self.assertEqual(int(self.client.session['_auth_user_id']), admin_user.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard.html')
        self.assertContains(response, 'site-message-success')
        self.assertContains(response, 'notifications.js')
        self.assertContains(response, 'Profit by month')

    def test_dashboard_monthly_profit_chart_uses_sales_and_expenses(self):
        admin_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.car.status = 'sold'
        self.car.save()
        Purchase.objects.create(
            car=self.car,
            seller_name='Seller',
            buying_price=100000,
        )
        Expense.objects.create(
            car=self.car,
            description='Repairs',
            amount=10000,
        )
        Sale.objects.create(
            car=self.car,
            buyer_name='Buyer',
            sale_price=125000,
            date_sold=timezone.localdate(),
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse('webapp:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Profit by month')
        self.assertContains(response, '₱15,000')
        self.assertContains(response, '>15</div>')
        self.assertContains(response, timezone.localdate().strftime('%b'))

    def test_staff_signin_redirects_to_garage_dashboard(self):
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            password='SolidPassword2026!',
            is_staff=True,
            role='admin',
        )

        response = self.client.post(
            reverse('webapp:sign_in'),
            {'username': 'staff@example.com', 'password': 'SolidPassword2026!'},
        )

        self.assertRedirects(response, reverse('webapp:dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), staff_user.pk)

    def test_buyer_cannot_access_garage_dashboard(self):
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(buyer)

        response = self.client.get(reverse('webapp:dashboard'))

        self.assertRedirects(response, reverse('webapp:home'))

    def test_car_financials_is_reached_from_inventory_not_a_sidebar_tab(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('webapp:dashboard'))

        self.assertContains(response, reverse('webapp:inventory'))
        self.assertContains(response, reverse('webapp:inquiries'))
        self.assertContains(response, reverse('webapp:people'))
        self.assertNotContains(response, 'Purchases, expenses, sales')
        self.assertNotContains(response, '/admin/webapp/')

        inventory_response = self.client.get(reverse('webapp:inventory'))

        self.assertEqual(inventory_response.status_code, 200)
        self.assertContains(inventory_response, reverse('webapp:car_financials', args=[self.car.pk]))
        self.assertContains(inventory_response, 'Purchases, expenses, sales')
        self.assertNotContains(inventory_response, '/garage/financials/')

    def test_people_tabs_list_accounts_by_role(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
            first_name='Regular',
            last_name='Buyer',
        )
        User.objects.create_user(
            username='manager@example.com',
            email='manager@example.com',
            password='SolidPassword2026!',
            first_name='Garage',
            last_name='Manager',
            role='admin',
            is_staff=True,
        )
        self.client.force_login(staff_user)

        buyers_response = self.client.get(reverse('webapp:people'), {'role': 'buyer'})
        admins_response = self.client.get(reverse('webapp:people'), {'role': 'admin'})

        self.assertContains(buyers_response, 'buyer@example.com')
        self.assertNotContains(buyers_response, 'manager@example.com')
        self.assertContains(buyers_response, 'data-live-search')
        self.assertContains(buyers_response, 'people-list-wrap')
        self.assertContains(buyers_response, 'Export to PDF')
        self.assertContains(buyers_response, 'role=buyer')
        self.assertNotContains(buyers_response, '>Search</button>')
        self.assertContains(admins_response, 'manager@example.com')
        self.assertNotContains(admins_response, 'buyer@example.com')

    def test_people_export_downloads_role_and_search_filtered_pdf(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        User.objects.create_user(
            username='manager@example.com',
            email='manager@example.com',
            password='SolidPassword2026!',
            first_name='Garage',
            last_name='Manager',
            role='admin',
            is_staff=True,
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:people'),
            {'export': 'pdf', 'role': 'admin', 'q': 'manager'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="people-admin.pdf"',
        )
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertIn(b'/MediaBox [ 0 0 595.2756 841.8898 ]', response.content)
        self.assertIn(b'/Subtype /Image', response.content)

    def test_people_live_search_returns_filtered_rows_without_full_page(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        matching_account = User.objects.create_user(
            username='maria@example.com',
            email='maria@example.com',
            password='SolidPassword2026!',
            first_name='Maria',
            last_name='Santos',
        )
        User.objects.create_user(
            username='alex@example.com',
            email='alex@example.com',
            password='SolidPassword2026!',
            first_name='Alex',
            last_name='Rivera',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:people'),
            {'role': 'buyer', 'q': 'maria'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'people-results.html')
        self.assertContains(response, 'maria@example.com')
        self.assertNotContains(response, 'alex@example.com')
        self.assertContains(
            response,
            reverse('webapp:account_edit', args=[matching_account.pk]),
        )

    def test_superuser_can_manually_create_admin_account(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:account_add'),
            {
                'full_name': 'New Manager',
                'email': 'manager@example.com',
                'phone': '09123456789',
                'role': 'admin',
                'password1': 'SolidPassword2026!',
                'password2': 'SolidPassword2026!',
            },
        )

        self.assertRedirects(response, reverse('webapp:people'))
        account = User.objects.get(email='manager@example.com')
        self.assertEqual(account.role, 'admin')
        self.assertTrue(account.is_staff)
        self.assertFalse(account.is_superuser)

    def test_people_page_has_edit_and_active_state_actions(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('webapp:people'), {'role': 'buyer'})

        self.assertContains(response, reverse('webapp:account_edit', args=[buyer.pk]))
        self.assertContains(response, reverse('webapp:account_toggle_active', args=[buyer.pk]))
        self.assertContains(response, reverse('webapp:account_remove', args=[buyer.pk]))
        self.assertContains(response, 'Deactivate')
        self.assertContains(response, 'class="link table-action">Deactivate</button>')
        self.assertContains(response, 'class="link table-action">Remove</button>')
        self.assertContains(response, 'data-confirmation-action-label="Remove account"')
        self.assertContains(response, '<dialog class="confirm-dialog" id="confirmation-dialog"')
        self.assertContains(response, 'data-confirmation-title="Deactivate this account?"')
        self.assertContains(response, 'existing inquiries and account history will be kept')
        self.assertContains(response, 'data-confirmation-submit')

    def test_staff_can_edit_account_name_email_and_phone(self):
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            password='SolidPassword2026!',
            role='admin',
            is_staff=True,
        )
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:account_edit', args=[buyer.pk]),
            {
                'full_name': 'Updated Buyer',
                'email': 'updated@example.com',
                'phone': '09123456789',
            },
        )

        self.assertRedirects(response, reverse('webapp:people'))
        buyer.refresh_from_db()
        self.assertEqual(buyer.get_full_name(), 'Updated Buyer')
        self.assertEqual(buyer.email, 'updated@example.com')
        self.assertEqual(buyer.username, 'updated@example.com')
        self.assertEqual(buyer.phone, '09123456789')

    def test_staff_can_deactivate_and_reactivate_account_without_deleting_history(self):
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            password='SolidPassword2026!',
            role='admin',
            is_staff=True,
        )
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='Is this car available?',
        )
        previous_inactivity_reset = buyer.inactivity_reset_at
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:account_toggle_active', args=[buyer.pk]),
        )

        self.assertRedirects(response, reverse('webapp:people'))
        buyer.refresh_from_db()
        self.assertFalse(buyer.is_active)
        self.assertTrue(Inquiry.objects.filter(pk=inquiry.pk, buyer=buyer).exists())

        self.client.post(reverse('webapp:account_toggle_active', args=[buyer.pk]))
        buyer.refresh_from_db()
        self.assertTrue(buyer.is_active)
        self.assertGreater(buyer.inactivity_reset_at, previous_inactivity_reset)

    def test_staff_can_remove_account_and_related_history(self):
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            password='SolidPassword2026!',
            role='admin',
            is_staff=True,
        )
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='Is this car available?',
        )
        self.client.force_login(staff_user)

        get_response = self.client.get(
            reverse('webapp:account_remove', args=[buyer.pk]),
        )
        self.assertRedirects(get_response, reverse('webapp:people'))
        self.assertTrue(User.objects.filter(pk=buyer.pk).exists())

        response = self.client.post(
            reverse('webapp:account_remove', args=[buyer.pk]),
        )

        self.assertRedirects(response, reverse('webapp:people'))
        self.assertFalse(User.objects.filter(pk=buyer.pk).exists())
        self.assertFalse(Inquiry.objects.filter(pk=inquiry.pk).exists())

    def test_staff_cannot_deactivate_self_or_superuser(self):
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            password='SolidPassword2026!',
            role='admin',
            is_staff=True,
        )
        superuser = User.objects.create_superuser(
            username='root@example.com',
            email='root@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        self.client.post(reverse('webapp:account_toggle_active', args=[staff_user.pk]))
        self.client.post(reverse('webapp:account_toggle_active', args=[superuser.pk]))
        self.client.post(reverse('webapp:account_remove', args=[staff_user.pk]))
        self.client.post(reverse('webapp:account_remove', args=[superuser.pk]))

        staff_user.refresh_from_db()
        superuser.refresh_from_db()
        self.assertTrue(staff_user.is_active)
        self.assertTrue(superuser.is_active)

    def test_staff_can_manually_create_buyer_but_not_admin(self):
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            password='SolidPassword2026!',
            role='admin',
            is_staff=True,
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:account_add'),
            {
                'full_name': 'New Buyer',
                'email': 'newbuyer@example.com',
                'phone': '',
                'role': 'admin',
                'password1': 'SolidPassword2026!',
                'password2': 'SolidPassword2026!',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(User.objects.filter(email='newbuyer@example.com').exists())

    def test_buyer_cannot_access_people_management(self):
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(buyer)

        response = self.client.get(reverse('webapp:people'))

        self.assertRedirects(response, reverse('webapp:home'))

    def test_staff_can_open_custom_inventory_page(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('webapp:inventory'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory.html')
        self.assertContains(response, 'rel="icon" type="image/png"')
        self.assertContains(response, 'class="table-wrap inventory-table-wrap"')
        self.assertContains(response, 'aria-label="Car inventory"')
        self.assertContains(response, 'Toyota Vios')
        self.assertContains(response, reverse('webapp:car_edit', args=[self.car.pk]))
        self.assertContains(response, reverse('webapp:car_financials', args=[self.car.pk]))
        self.assertContains(response, reverse('webapp:car_delete', args=[self.car.pk]))
        self.assertContains(response, 'Export to PDF')
        self.assertContains(response, 'class="garage-toolbar inventory-toolbar"')
        self.assertLess(
            response.content.index(b'>Clear</a>'),
            response.content.index(b'>Export to PDF</a>'),
        )
        self.assertContains(response, '?export=pdf')
        self.assertContains(response, 'data-submit-on-change')
        self.assertContains(response, 'data-inventory-search')
        self.assertContains(response, 'id="inventory-results"')
        self.assertNotContains(response, '>Filter</button>')
        self.assertContains(response, '<dialog class="confirm-dialog" id="confirmation-dialog"')
        self.assertContains(response, 'data-confirmation-title="Delete this car?"')
        self.assertContains(response, 'its purchase, expenses, sale, documents, photos, and inquiries')

    def test_inventory_export_downloads_filtered_pdf(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        Car.objects.create(
            brand='Honda',
            model='Civic',
            variant='RS',
            year=2020,
            transmission='automatic',
            fuel='gasoline',
            mileage=30000,
            asking_price=800000,
            status='repair',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:inventory'),
            {'export': 'pdf', 'status': 'available', 'q': 'Toyota'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="cars-inventory.pdf"',
        )
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertGreater(len(response.content), 1000)
        self.assertIn(b'/MediaBox [ 0 0 595.2756 841.8898 ]', response.content)
        self.assertIn(b'Bol Garage', response.content)
        self.assertIn(b'/Subtype /Image', response.content)

    def test_inventory_live_search_returns_filtered_rows_without_full_page(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        matching_car = self.car
        matching_car.brand = 'Toyota'
        matching_car.save()
        Car.objects.create(
            brand='Honda',
            model='Civic',
            variant='RS',
            year=2020,
            transmission='automatic',
            fuel='gasoline',
            mileage=30000,
            asking_price=800000,
            status='repair',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:inventory'),
            {'q': 'Toyota', 'status': 'available'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory-results.html')
        self.assertContains(response, '2018 Toyota Vios')
        self.assertNotContains(response, 'Honda Civic')
        self.assertContains(
            response,
            reverse('webapp:car_financials', args=[matching_car.pk]),
        )

    def test_staff_can_delete_car_and_all_related_records(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        image_data = BytesIO()
        Image.new('RGB', (2, 2), color='white').save(image_data, format='PNG')
        image_bytes = image_data.getvalue()
        self.client.force_login(staff_user)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            photo = CarPhoto.objects.create(
                car=self.car,
                image=SimpleUploadedFile('car.png', image_bytes, content_type='image/png'),
            )
            expense = Expense.objects.create(
                car=self.car,
                description='Repair',
                amount=1000,
                receipt=SimpleUploadedFile('receipt.png', image_bytes, content_type='image/png'),
            )
            purchase = Purchase.objects.create(
                car=self.car,
                seller_name='Seller',
                buying_price=100000,
            )
            sale = Sale.objects.create(
                car=self.car,
                buyer_name='Buyer',
                sale_price=120000,
            )
            document = CarDocument.objects.create(
                car=self.car,
                doc_type='orcr',
                file=SimpleUploadedFile('orcr.pdf', b'document'),
            )
            Inquiry.objects.create(
                car=self.car,
                buyer=buyer,
                message='Interested',
            )
            file_references = [
                (photo.image.storage, photo.image.name),
                (expense.receipt.storage, expense.receipt.name),
                (document.file.storage, document.file.name),
            ]

            response = self.client.post(
                reverse('webapp:car_delete', args=[self.car.pk]),
                follow=True,
            )

            self.assertRedirects(response, reverse('webapp:inventory'))
            self.assertFalse(Car.objects.filter(pk=self.car.pk).exists())
            self.assertFalse(Purchase.objects.filter(pk=purchase.pk).exists())
            self.assertFalse(Expense.objects.filter(pk=expense.pk).exists())
            self.assertFalse(Sale.objects.filter(pk=sale.pk).exists())
            self.assertFalse(CarDocument.objects.filter(pk=document.pk).exists())
            self.assertFalse(CarPhoto.objects.filter(pk=photo.pk).exists())
            self.assertFalse(Inquiry.objects.filter(car_id=self.car.pk).exists())
            for storage, filename in file_references:
                self.assertFalse(storage.exists(filename))
            self.assertContains(response, 'and its related records were permanently deleted.')

    def test_car_delete_requires_post(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('webapp:car_delete', args=[self.car.pk]))

        self.assertRedirects(response, reverse('webapp:inventory'))
        self.assertTrue(Car.objects.filter(pk=self.car.pk).exists())

    def test_staff_can_open_dynamic_car_financials_page(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        Purchase.objects.create(
            car=self.car,
            seller_name='Test Seller',
            seller_contact='09123456789',
            buying_price=395000,
        )
        expense = Expense.objects.create(
            car=self.car,
            description='Registration renewal',
            category='registration',
            amount=28000,
        )

        response = self.client.get(
            reverse('webapp:car_financials', args=[self.car.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'admin-car.html')
        self.assertContains(response, 'class="sidebar-menu-toggle"')
        self.assertContains(response, 'aria-controls="garage-navigation"')
        self.assertContains(response, 'garage-navigation.js')
        self.assertContains(response, reverse('webapp:car_financials_pdf', args=[self.car.pk]))
        self.assertContains(response, 'Export to PDF')
        self.assertContains(response, 'Reservation / downpayment')
        self.assertContains(response, 'Add payment')
        self.assertContains(response, 'Record a reservation fee or downpayment')
        self.assertContains(response, 'Create sale agreement')
        self.assertContains(response, 'A reservation or downpayment is not required')
        self.assertContains(response, 'name="buyer_address"')
        self.assertContains(response, 'name="account_name"')
        self.assertContains(response, 'No reservation or downpayment records yet.')
        self.assertContains(response, 'Upload signed sale agreements and signed copies of acknowledgment receipts here.')
        self.assertLess(
            response.content.index(b'Reservation / downpayment'),
            response.content.index(b'>Sale<'),
        )
        self.assertLess(
            response.content.index(b'badge-lg'),
            response.content.index(b'Export to PDF'),
        )
        self.assertContains(response, 'Repairs and expenses')
        self.assertContains(response, 'Test Seller')
        self.assertContains(response, 'Registration renewal')
        self.assertContains(response, '<div>Date</div><div>Item</div><div>Category</div><div>Receipt</div><div>Actions</div><div class="right">Amount</div>')
        self.assertContains(response, '<div class="expense-actions">')
        self.assertContains(response, '<dialog class="confirm-dialog" id="confirmation-dialog"')
        self.assertContains(response, 'data-confirmation-message="This will permanently remove this expense and its receipt, if one is attached.')
        self.assertContains(response, 'data-confirmation-cancel')
        self.assertContains(response, 'data-confirmation-submit')
        self.assertContains(response, f'data-expense-id="{expense.pk}"')
        self.assertContains(response, 'name="expense_id"')
        self.assertContains(response, '<dialog class="expense-edit-dialog" id="expense-edit-dialog"')
        self.assertNotContains(response, 'id="edit-expense-')
        self.assertContains(response, '₱42,000')
        self.assertContains(response, 'Expected profit')
        self.assertContains(response, 'type="date"', count=6)
        today = timezone.localdate().isoformat()
        self.assertContains(response, f'name="date_bought" value="{today}"')
        self.assertContains(response, f'name="date" value="{today}"')
        self.assertContains(response, f'name="date_received" value="{today}"')
        self.assertContains(response, f'name="date_sold" value="{today}"')
        self.assertNotContains(response, 'Search brand, model, plate or chassis')
        self.assertContains(
            response,
            f'<a href="{reverse("webapp:inventory")}" class="active">Cars and inventory</a>',
        )

    def test_sale_date_is_under_buyer_address(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        Sale.objects.create(
            car=self.car,
            buyer_name='Chris Gae',
            buyer_address='Bacoor, Cavite',
            buyer_contact='091234565124',
            sale_price=265000,
            date_sold=timezone.localdate(),
        )

        response = self.client.get(
            reverse('webapp:car_financials', args=[self.car.pk]),
        )

        self.assertContains(response, '<div class="facts sale-facts">')
        self.assertContains(response, 'Buyer address')
        self.assertContains(response, 'Date sold')

    def test_staff_can_download_car_financial_report_pdf(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        Purchase.objects.create(
            car=self.car,
            seller_name='Maria Santos',
            seller_contact='09123456789',
            date_bought=timezone.localdate(),
            buying_price=395000,
            notes='First owner',
        )
        Expense.objects.create(
            car=self.car,
            description='Registration renewal',
            category='registration',
            amount=28000,
            receipt='receipts/registration.png',
        )
        Sale.objects.create(
            car=self.car,
            buyer_name='Alex Cruz',
            buyer_contact='09987654321',
            sale_price=450000,
            date_sold=timezone.localdate(),
            notes='Paid in full',
        )

        response = self.client.get(
            reverse('webapp:car_financials_pdf', args=[self.car.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="car-{self.car.pk}-financial-report.pdf"',
        )
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertGreater(len(response.content), 1000)
        self.assertIn(b'/MediaBox [ 0 0 595.2756 841.8898 ]', response.content)
        self.assertIn(b'/Subtype /Image', response.content)

    def test_car_financial_report_supports_car_without_purchase_or_sale(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:car_financials_pdf', args=[self.car.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))

    def test_staff_can_add_edit_and_delete_multiple_car_payments(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        url = reverse('webapp:car_financials', args=[self.car.pk])
        first_payment = {
            'buyer_name': 'Alex Cruz',
            'buyer_contact': '09123456789',
            'account_name': 'Alex Cruz',
            'payment_type': 'reservation',
            'amount': '5000.00',
            'date_received': timezone.localdate().isoformat(),
            'payment_method': 'Cash',
            'reference_number': 'RES-100',
            'notes': 'Reservation fee',
        }
        response = self.client.post(url, {'action': 'payment', **first_payment})
        self.assertRedirects(response, url)
        payment = CarPayment.objects.get(car=self.car)
        self.assertEqual(payment.buyer_name, 'Alex Cruz')
        self.assertEqual(payment.payment_type, 'reservation')
        self.assertEqual(payment.amount, Decimal('5000.00'))

        second_payment = {**first_payment, 'payment_type': 'downpayment', 'amount': '25000.00'}
        self.client.post(url, {'action': 'payment', **second_payment})
        self.assertEqual(CarPayment.objects.filter(car=self.car).count(), 2)

        edited_payment = {
            'edit-payment-buyer_name': 'Alex C. Cruz',
            'edit-payment-buyer_contact': '09123456789',
            'edit-payment-account_name': 'Alex C. Cruz',
            'edit-payment-payment_type': 'reservation',
            'edit-payment-amount': '6000.00',
            'edit-payment-date_received': timezone.localdate().isoformat(),
            'edit-payment-payment_method': 'Bank transfer',
            'edit-payment-reference_number': 'BANK-6000',
            'edit-payment-notes': 'Reservation fee',
        }
        response = self.client.post(
            url,
            {
                'action': 'edit_payment',
                'payment_id': payment.pk,
                **edited_payment,
            },
        )
        self.assertRedirects(response, url)
        payment.refresh_from_db()
        self.assertEqual(payment.buyer_name, 'Alex C. Cruz')
        self.assertEqual(payment.amount, Decimal('6000.00'))
        self.assertEqual(payment.payment_method, 'Bank transfer')

        response = self.client.post(
            url,
            {'action': 'delete_payment', 'payment_id': payment.pk},
        )
        self.assertRedirects(response, url)
        self.assertFalse(CarPayment.objects.filter(pk=payment.pk).exists())
        self.assertEqual(CarPayment.objects.filter(car=self.car).count(), 1)

    def test_payment_amount_must_be_greater_than_zero(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:car_financials', args=[self.car.pk]),
            {
                'action': 'payment',
                'buyer_name': 'Alex Cruz',
                'payment_type': 'reservation',
                'amount': '0',
                'date_received': timezone.localdate().isoformat(),
                'payment_method': 'Cash',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter an amount greater than zero.')
        self.assertEqual(CarPayment.objects.count(), 0)

    def test_staff_can_download_acknowledgment_receipt_for_payment(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        payment = CarPayment.objects.create(
            car=self.car,
            buyer_name='Alex Cruz',
            buyer_contact='09123456789',
            account_name='Alex Cruz Bank',
            payment_type='downpayment',
            amount=25000,
            date_received=timezone.localdate(),
            payment_method='Bank transfer',
            reference_number='BANK-25000',
        )

        response = self.client.get(
            reverse(
                'webapp:car_payment_receipt_pdf',
                args=[self.car.pk, payment.pk],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="acknowledgment-receipt-BG-{payment.pk}.pdf"',
        )
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertIn(b'/Subtype /Image', response.content)
        receipt_text = PdfReader(BytesIO(response.content)).pages[0].extract_text()
        self.assertIn('Acknowledgement Receipt', receipt_text)
        self.assertIn('Company Copy', receipt_text)
        self.assertIn('Client Copy', receipt_text)
        self.assertIn('Alex Cruz', receipt_text)
        self.assertIn('Alex Cruz Bank', receipt_text)
        self.assertIn('Vios', receipt_text)
        self.assertIn('25,000.00', receipt_text)
        self.assertIn('Twenty five thousand pesos', receipt_text)

    def test_staff_can_download_sale_agreement_for_walk_in_buyer_without_payment(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        Sale.objects.create(
            car=self.car,
            buyer_name='Walk-in Buyer',
            buyer_address='123 Mabini Street, Manila',
            buyer_contact='09123456789',
            sale_price=450000,
            date_sold=timezone.localdate(),
        )

        response = self.client.get(
            reverse('webapp:car_sale_agreement_pdf', args=[self.car.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="vehicle-sale-agreement-car-{self.car.pk}.pdf"',
        )
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertIn(b'/Subtype /Image', response.content)
        self.assertEqual(CarPayment.objects.filter(car=self.car).count(), 0)
        agreement_text = PdfReader(BytesIO(response.content)).pages[0].extract_text()
        self.assertIn('VEHICLE SALE ACKNOWLEDGEMENT', agreement_text)
        self.assertIn('Walk-in Buyer', agreement_text)
        self.assertIn('123 Mabini Street, Manila', agreement_text)
        self.assertIn('Toyota Vios', agreement_text)
        self.assertIn('has been received in full.', agreement_text)

    def test_sale_agreement_requires_saved_sale_details(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        financials_url = reverse('webapp:car_financials', args=[self.car.pk])

        response = self.client.get(
            reverse('webapp:car_sale_agreement_pdf', args=[self.car.pk]),
            follow=True,
        )

        self.assertEqual(response.redirect_chain, [(financials_url, 302)])
        self.assertContains(response, 'Record the sale details before creating a sale agreement.')

    def test_expense_receipt_link_opens_image_preview_modal(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        image_data = BytesIO()
        Image.new('RGB', (2, 2), color='white').save(image_data, format='PNG')

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            Expense.objects.create(
                car=self.car,
                description='Receipt test',
                amount=1200,
                receipt=SimpleUploadedFile(
                    'receipt.png',
                    image_data.getvalue(),
                    content_type='image/png',
                ),
            )

            response = self.client.get(
                reverse('webapp:car_financials', args=[self.car.pk]),
            )

            self.assertContains(response, 'data-receipt-preview')
            self.assertContains(response, 'data-receipt-alt="Receipt for Receipt test"')
            self.assertContains(
                response,
                '<dialog class="receipt-dialog" id="receipt-preview-dialog"',
            )
            self.assertContains(response, 'aria-label="Close image preview"')

    def test_document_images_open_preview_and_can_be_removed(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        image_data = BytesIO()
        Image.new('RGB', (2, 2), color='white').save(image_data, format='PNG')

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            document = CarDocument.objects.create(
                car=self.car,
                doc_type='deed_seller',
                file=SimpleUploadedFile(
                    'seller-deed.png',
                    image_data.getvalue(),
                    content_type='image/png',
                ),
            )
            file_name = document.file.name
            response = self.client.get(
                reverse('webapp:car_financials', args=[self.car.pk]),
            )

            self.assertContains(response, 'data-receipt-preview')
            self.assertContains(response, 'data-receipt-alt="Deed of sale (from seller) document"')
            self.assertContains(
                response,
                reverse('webapp:document_delete', args=[self.car.pk, document.pk]),
            )
            self.assertContains(response, 'aria-label="Remove Deed of sale (from seller) document"')
            self.assertContains(response, 'data-confirmation-title="Remove this document?"')

            response = self.client.post(
                reverse('webapp:document_delete', args=[self.car.pk, document.pk]),
                follow=True,
            )

            self.assertRedirects(
                response,
                reverse('webapp:car_financials', args=[self.car.pk]),
            )
            self.assertFalse(CarDocument.objects.filter(pk=document.pk).exists())
            self.assertFalse(document.file.storage.exists(file_name))
            self.assertContains(response, 'Document removed.')

    def test_document_delete_requires_post(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        document = CarDocument.objects.create(
            car=self.car,
            doc_type='orcr',
            file='documents/orcr.pdf',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:document_delete', args=[self.car.pk, document.pk]),
        )

        self.assertRedirects(
            response,
            reverse('webapp:car_financials', args=[self.car.pk]),
        )
        self.assertTrue(CarDocument.objects.filter(pk=document.pk).exists())

    def test_staff_can_add_expense_from_car_financials(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:car_financials', args=[self.car.pk]),
            {
                'action': 'expense',
                'description': 'Brake pads',
                'category': 'parts',
                'date': timezone.localdate().isoformat(),
                'amount': '6500',
            },
        )

        self.assertRedirects(
            response,
            reverse('webapp:car_financials', args=[self.car.pk]),
        )
        self.assertTrue(
            Expense.objects.filter(car=self.car, description='Brake pads').exists(),
        )

    def test_staff_can_edit_expense_and_add_receipt_later(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        expense = Expense.objects.create(
            car=self.car,
            description='Gasoline',
            category='other',
            amount=5000,
            date=timezone.localdate(),
        )
        self.client.force_login(staff_user)
        image_data = BytesIO()
        Image.new('RGB', (2, 2), color='white').save(image_data, format='PNG')

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('webapp:car_financials', args=[self.car.pk]),
                {
                    'action': 'edit_expense',
                    'expense_id': str(expense.pk),
                    'description': 'Gasoline for test drive',
                    'category': 'other',
                    'date': timezone.localdate().isoformat(),
                    'amount': '5500',
                    'receipt': SimpleUploadedFile(
                        'gas-receipt.png',
                        image_data.getvalue(),
                        content_type='image/png',
                    ),
                },
            )

            self.assertRedirects(
                response,
                reverse('webapp:car_financials', args=[self.car.pk]),
            )
            expense.refresh_from_db()
            self.assertEqual(expense.description, 'Gasoline for test drive')
            self.assertEqual(expense.amount, 5500)
            self.assertTrue(expense.receipt.name.endswith('gas-receipt.png'))

    def test_invalid_expense_edit_keeps_edit_form_open(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        expense = Expense.objects.create(
            car=self.car,
            description='Gasoline',
            category='other',
            amount=5000,
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:car_financials', args=[self.car.pk]),
            {
                'action': 'edit_expense',
                'expense_id': str(expense.pk),
                'description': '',
                'category': 'other',
                'date': timezone.localdate().isoformat(),
                'amount': '5000',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-open-on-load')
        self.assertContains(response, f'value="{expense.pk}" id="expense-edit-id"')
        self.assertContains(response, 'This field is required.')
        expense.refresh_from_db()
        self.assertEqual(expense.description, 'Gasoline')

    def test_staff_can_delete_expense_and_its_receipt(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        image_data = BytesIO()
        Image.new('RGB', (2, 2), color='white').save(image_data, format='PNG')
        receipt = SimpleUploadedFile(
            'receipt.png',
            image_data.getvalue(),
            content_type='image/png',
        )

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            expense = Expense.objects.create(
                car=self.car,
                description='Incorrect expense',
                amount=10000,
                receipt=receipt,
            )
            receipt_name = expense.receipt.name
            response = self.client.post(
                reverse(
                    'webapp:expense_delete',
                    args=[self.car.pk, expense.pk],
                ),
                follow=True,
            )

            self.assertRedirects(
                response,
                reverse('webapp:car_financials', args=[self.car.pk]),
            )
            self.assertFalse(Expense.objects.filter(pk=expense.pk).exists())
            self.assertFalse(expense.receipt.storage.exists(receipt_name))
            self.assertContains(response, 'Expense &quot;Incorrect expense&quot; was deleted.')

    def test_expense_delete_requires_post(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        expense = Expense.objects.create(
            car=self.car,
            description='Keep this expense',
            amount=1000,
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:expense_delete', args=[self.car.pk, expense.pk]),
        )

        self.assertRedirects(
            response,
            reverse('webapp:car_financials', args=[self.car.pk]),
        )
        self.assertTrue(Expense.objects.filter(pk=expense.pk).exists())

    def test_sale_entry_marks_car_sold_and_uses_actual_profit(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        Purchase.objects.create(
            car=self.car,
            seller_name='Test Seller',
            buying_price=395000,
        )
        Expense.objects.create(
            car=self.car,
            description='Repairs',
            amount=28000,
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:car_financials', args=[self.car.pk]),
            {
                'action': 'sale',
                'buyer_name': 'Test Buyer',
                'buyer_contact': '09123456789',
                'sale_price': '465000',
                'date_sold': timezone.localdate().isoformat(),
                'notes': '',
            },
        )

        self.assertRedirects(
            response,
            reverse('webapp:car_financials', args=[self.car.pk]),
        )
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, 'sold')
        self.assertEqual(self.car.sale.sale_price, 465000)
        financials_response = self.client.get(
            reverse('webapp:car_financials', args=[self.car.pk]),
        )
        self.assertContains(financials_response, 'Final profit')
        self.assertContains(financials_response, '₱42,000')

    def test_saving_sale_model_marks_car_sold(self):
        Sale.objects.create(
            car=self.car,
            buyer_name='Buyer',
            sale_price=450000,
        )

        self.car.refresh_from_db()
        self.assertEqual(self.car.status, 'sold')

    def test_status_cannot_be_set_to_sold_without_sale(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:car_financials', args=[self.car.pk]),
            {'action': 'status', 'status': 'sold'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Record the sale details before setting this car to Sold.')
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, 'available')

    def test_car_cannot_be_made_available_without_asking_price(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.car.status = 'incoming'
        self.car.asking_price = 0
        self.car.save()
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:car_financials', args=[self.car.pk]),
            {'action': 'status', 'status': 'available'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter an asking price before making this car available.')
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, 'incoming')

    def test_editing_sold_car_displays_warning(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.car.status = 'sold'
        self.car.save()
        Sale.objects.create(
            car=self.car,
            buyer_name='Buyer',
            sale_price=450000,
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('webapp:car_edit', args=[self.car.pk]))

        self.assertContains(response, 'This car is sold. Editing its details or photos may affect its historical listing and records.')

        financial_response = self.client.get(
            reverse('webapp:car_financials', args=[self.car.pk]),
        )
        self.assertContains(financial_response, 'Changes to its purchase, expenses, or sale will change its recorded final profit.')

    def test_car_edit_form_enforces_status_requirements(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        edit_url = reverse('webapp:car_edit', args=[self.car.pk])
        car_data = {
            'brand': self.car.brand,
            'model': self.car.model,
            'variant': self.car.variant,
            'year': self.car.year,
            'color': self.car.color,
            'transmission': self.car.transmission,
            'fuel': self.car.fuel,
            'mileage': self.car.mileage,
            'plate_number': self.car.plate_number,
            'engine_number': self.car.engine_number,
            'chassis_number': self.car.chassis_number,
            'description': self.car.description,
        }

        no_price_response = self.client.post(
            edit_url,
            {**car_data, 'asking_price': '0', 'status': 'available'},
        )
        self.assertContains(
            no_price_response,
            'Enter an asking price before making this car available.',
        )
        self.car.refresh_from_db()
        self.assertEqual(self.car.asking_price, 465000)

        no_sale_response = self.client.post(
            edit_url,
            {**car_data, 'asking_price': '465000', 'status': 'sold'},
        )
        self.assertContains(
            no_sale_response,
            'Record the sale details before setting this car to Sold.',
        )
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, 'available')

    def test_staff_can_add_car_in_custom_interface(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:car_add'),
            {
                'brand': 'Honda',
                'model': 'Civic',
                'variant': '1.8 S',
                'year': 2017,
                'color': 'Black',
                'transmission': 'automatic',
                'fuel': 'gasoline',
                'mileage': 71000,
                'plate_number': '',
                'engine_number': '',
                'chassis_number': '',
                'asking_price': '598000',
                'description': 'Clean condition.',
                'status': 'available',
            },
        )

        self.assertRedirects(response, reverse('webapp:inventory'))
        self.assertTrue(Car.objects.filter(brand='Honda', model='Civic').exists())

    def test_staff_can_upload_multiple_car_photos(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(staff_user)
        image_data = BytesIO()
        Image.new('RGB', (2, 2), color='white').save(image_data, format='PNG')
        image_bytes = image_data.getvalue()

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('webapp:car_add'),
                {
                    'brand': 'Honda',
                    'model': 'Civic',
                    'variant': '1.8 S',
                    'year': 2017,
                    'color': 'Black',
                    'transmission': 'automatic',
                    'fuel': 'gasoline',
                    'mileage': 71000,
                    'plate_number': '',
                    'engine_number': '',
                    'chassis_number': '',
                    'asking_price': '598000',
                    'description': 'Clean condition.',
                    'status': 'available',
                    'photos': [
                        SimpleUploadedFile('exterior.png', image_bytes, content_type='image/png'),
                        SimpleUploadedFile('interior.png', image_bytes, content_type='image/png'),
                    ],
                },
            )

            self.assertRedirects(response, reverse('webapp:inventory'))
            car = Car.objects.get(brand='Honda', model='Civic')
            photos = list(car.photos.order_by('order'))
            self.assertEqual(len(photos), 2)
            self.assertEqual([photo.order for photo in photos], [0, 1])
            self.assertTrue(photos[0].image.name.endswith('exterior.png'))
            self.assertTrue(photos[1].image.name.endswith('interior.png'))

    def test_staff_can_remove_a_car_photo_and_reorder_remaining_photos(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        first_photo = CarPhoto.objects.create(
            car=self.car,
            image='cars/exterior.jpg',
            order=0,
        )
        second_photo = CarPhoto.objects.create(
            car=self.car,
            image='cars/interior.jpg',
            order=1,
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:car_photo_delete', args=[self.car.pk, first_photo.pk]),
        )

        self.assertRedirects(response, reverse('webapp:car_edit', args=[self.car.pk]))
        self.assertFalse(CarPhoto.objects.filter(pk=first_photo.pk).exists())
        second_photo.refresh_from_db()
        self.assertEqual(second_photo.order, 0)

    def test_car_photo_removal_requires_post(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        photo = CarPhoto.objects.create(car=self.car, image='cars/exterior.jpg')
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:car_photo_delete', args=[self.car.pk, photo.pk]),
        )

        self.assertRedirects(response, reverse('webapp:car_edit', args=[self.car.pk]))
        self.assertTrue(CarPhoto.objects.filter(pk=photo.pk).exists())

    def test_staff_can_update_inquiry_status_in_custom_interface(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='Can I see the car?',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:inquiry_status', args=[inquiry.pk]),
            {'status': 'contacted'},
        )

        self.assertRedirects(
            response,
            f"{reverse('webapp:inquiries')}?status=contacted&inquiry={inquiry.pk}",
        )
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.status, 'contacted')

    def test_inquiry_page_shows_status_tabs_and_selected_detail(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
            first_name='Maria',
            last_name='Santos',
            phone='09123456789',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='reserve',
            message='Can I view the car this week?',
        )
        Inquiry.objects.create(
            car=self.car,
            buyer=User.objects.create_user(
                username='second-buyer@example.com',
                email='second-buyer@example.com',
                password='SolidPassword2026!',
            ),
            message='Is it still available?',
            status='contacted',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:inquiries'),
            {'status': 'new', 'inquiry': inquiry.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="inquiry-tabs"')
        self.assertContains(response, 'All (2)')
        self.assertContains(response, 'New (1)')
        self.assertContains(response, 'Contacted (1)')
        self.assertContains(response, 'class="inquiry-workspace"')
        self.assertContains(response, 'Maria Santos')
        self.assertContains(response, 'Can I view the car this week?')
        self.assertContains(response, 'Set car to Reserved')
        self.assertContains(response, 'Reply by email')
        inquiry_compose_params = parse_qs(urlparse(response.context['reply_compose_url']).query)
        self.assertEqual(inquiry_compose_params['to'], ['buyer@example.com'])
        self.assertEqual(inquiry_compose_params['view'], ['cm'])
        self.assertEqual(
            inquiry_compose_params['su'],
            [f'Following up on your inquiry about {self.car}'],
        )
        self.assertIn('Can I view the car this week?', response.context['selected_inquiry'].message)
        self.assertContains(response, reverse('webapp:inquiry_delete', args=[inquiry.pk]))
        self.assertContains(response, 'Delete inquiry')
        self.assertContains(response, 'data-confirmation-form')
        self.assertContains(response, f'?status=new&amp;inquiry={inquiry.pk}')
        self.assertContains(response, 'class="inbox"')

    def test_staff_can_filter_and_view_cancelled_inquiries(self):
        staff_user = User.objects.create_superuser(
            username='cancelled-inquiry-admin@example.com',
            email='cancelled-inquiry-admin@example.com',
            password='SolidPassword2026!',
        )
        buyer = User.objects.create_user(
            username='cancelled-inquiry-buyer@example.com',
            email='cancelled-inquiry-buyer@example.com',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='I no longer need help.',
            status='cancelled',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:inquiries'),
            {'status': 'cancelled', 'inquiry': inquiry.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cancelled (1)')
        self.assertContains(response, 'I no longer need help.')
        self.assertEqual(response.context['selected_inquiry'].status, 'cancelled')

    def test_staff_can_delete_inquiry_and_preserve_status_filter(self):
        staff_user = User.objects.create_superuser(
            username='inquiry-delete-admin@example.com',
            email='inquiry-delete-admin@example.com',
            password='SolidPassword2026!',
        )
        buyer = User.objects.create_user(
            username='inquiry-delete-buyer@example.com',
            email='inquiry-delete-buyer@example.com',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='Please remove this inquiry.',
            status='new',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:inquiry_delete', args=[inquiry.pk]),
            {'status': 'new'},
            follow=True,
        )

        self.assertRedirects(
            response,
            f"{reverse('webapp:inquiries')}?status=new",
        )
        self.assertFalse(Inquiry.objects.filter(pk=inquiry.pk).exists())
        self.assertContains(response, 'Inquiry permanently deleted.')

    def test_inquiry_delete_requires_post_and_staff_access(self):
        staff_user = User.objects.create_superuser(
            username='inquiry-delete-method-admin@example.com',
            email='inquiry-delete-method-admin@example.com',
            password='SolidPassword2026!',
        )
        buyer = User.objects.create_user(
            username='inquiry-delete-method-buyer@example.com',
            email='inquiry-delete-method-buyer@example.com',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='inquiry',
            message='Please keep this inquiry.',
        )
        self.client.force_login(staff_user)

        response = self.client.get(
            reverse('webapp:inquiry_delete', args=[inquiry.pk]),
        )
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Inquiry.objects.filter(pk=inquiry.pk).exists())

        another_buyer = User.objects.create_user(
            username='inquiry-delete-unauthorized@example.com',
            email='inquiry-delete-unauthorized@example.com',
        )
        self.client.force_login(another_buyer)
        response = self.client.post(
            reverse('webapp:inquiry_delete', args=[inquiry.pk]),
        )
        self.assertRedirects(response, reverse('webapp:home'))
        self.assertTrue(Inquiry.objects.filter(pk=inquiry.pk).exists())

    def test_inquiry_list_scrolls_at_five_items(self):
        staff_user = User.objects.create_superuser(
            username='inquiry-scroll-admin@example.com',
            email='inquiry-scroll-admin@example.com',
            password='SolidPassword2026!',
        )
        buyer = User.objects.create_user(
            username='inquiry-scroll-buyer@example.com',
            email='inquiry-scroll-buyer@example.com',
        )
        for index in range(5):
            Inquiry.objects.create(
                car=self.car,
                buyer=buyer,
                kind='inquiry',
                message=f'Inquiry message {index}',
            )
        self.client.force_login(staff_user)

        response = self.client.get(reverse('webapp:inquiries'))

        self.assertContains(response, 'class="inbox inbox-scrollable"')

    def test_staff_can_reserve_car_from_inquiry_detail(self):
        staff_user = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        buyer = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        inquiry = Inquiry.objects.create(
            car=self.car,
            buyer=buyer,
            kind='reserve',
            message='I would like to reserve this car.',
        )
        self.client.force_login(staff_user)

        response = self.client.post(
            reverse('webapp:inquiry_reserve_car', args=[inquiry.pk]),
        )

        self.assertRedirects(
            response,
            f"{reverse('webapp:inquiries')}?inquiry={inquiry.pk}",
        )
        self.car.refresh_from_db()
        self.assertEqual(self.car.status, 'reserved')

    def test_invalid_signin_preserves_next_url(self):
        response = self.client.post(
            reverse('webapp:sign_in'),
            {
                'username': 'buyer@example.com',
                'password': 'incorrect',
                'next': reverse('webapp:car_detail', args=[self.car.pk]),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'name="next" value="{reverse("webapp:car_detail", args=[self.car.pk])}"',
        )

    def test_signout_ends_session(self):
        user = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(user)

        response = self.client.post(reverse('webapp:logout'))

        self.assertRedirects(response, reverse('webapp:home'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_signed_out_user_cannot_restore_garage_dashboard(self):
        admin = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(admin)

        dashboard_response = self.client.get(reverse('webapp:dashboard'))
        self.assertIn('no-store', dashboard_response['Cache-Control'])

        self.client.post(reverse('webapp:logout'))
        response = self.client.get(reverse('webapp:dashboard'))

        self.assertRedirects(
            response,
            f"{reverse('webapp:sign_in')}?next={reverse('webapp:dashboard')}",
        )
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_guest_inquiry_redirects_to_signin(self):
        response = self.client.post(
            reverse('webapp:submit_inquiry', args=[self.car.pk]),
            {'kind': 'inquiry', 'message': 'Can I view this car?'},
        )

        self.assertRedirects(
            response,
            f"{reverse('webapp:sign_in')}?next={reverse('webapp:submit_inquiry', args=[self.car.pk])}",
        )
        self.assertEqual(Inquiry.objects.count(), 0)

    @override_settings(
        SMTP_USERNAME='bolgarage123@gmail.com',
        SMTP_PASSWORD='test-app-password',
        DEFAULT_FROM_EMAIL='bolgarage123@gmail.com',
        CONTACT_NOTIFICATION_EMAIL='bolgarage123@gmail.com',
    )
    def test_signed_in_buyer_can_submit_reservation_request(self):
        user = User.objects.create_user(
            username='buyer@example.com',
            email='buyer@example.com',
            password='SolidPassword2026!',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('webapp:submit_inquiry', args=[self.car.pk]),
            {'kind': 'reserve', 'message': 'I would like to reserve this car.'},
        )

        self.assertRedirects(response, reverse('webapp:car_detail', args=[self.car.pk]))
        inquiry = Inquiry.objects.get()
        self.assertEqual(inquiry.buyer, user)
        self.assertEqual(inquiry.car, self.car)
        self.assertEqual(inquiry.kind, 'reserve')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['bolgarage123@gmail.com'])
        self.assertIn('reserve request', mail.outbox[0].subject.lower())
        self.assertIn('I would like to reserve this car.', mail.outbox[0].body)
        self.assertIn(
            f'/garage/inquiries/?status=new&inquiry={inquiry.pk}',
            mail.outbox[0].body,
        )
