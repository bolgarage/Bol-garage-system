from email.message import MIMEPart
from pathlib import Path

from django.contrib.auth import get_user_model
from django.urls import reverse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .notifications import send_welcome_email

LOGO_PATH = Path(__file__).parent / 'static' / 'media' / 'BG logo.png'


class GarageAccountAdapter(DefaultAccountAdapter):
    def render_mail(self, template_prefix, email, context, headers=None):
        message = super().render_mail(template_prefix, email, context, headers)
        if template_prefix == 'account/email/password_reset_key':
            logo = MIMEPart()
            logo.set_content(
                LOGO_PATH.read_bytes(),
                maintype='image',
                subtype='png',
                cid='<bol-garage-logo>',
                disposition='inline',
                filename='bol-garage-logo.png',
            )
            message.attach(logo)
        return message

    def get_login_redirect_url(self, request):
        if request.user.is_staff:
            return reverse('webapp:dashboard')
        return super().get_login_redirect_url(request)


class GarageSocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        if not user.is_staff:
            send_welcome_email(user)
        return user

    def _matching_staff_user(self, email):
        users = get_user_model().objects.filter(
            email__iexact=email,
            is_active=True,
            is_staff=True,
        )
        return users.get() if users.count() == 1 else None

    def authenticate_by_email(self, sociallogin):
        if sociallogin.provider.id == 'google':
            for email_address in sociallogin.email_addresses:
                if email_address.verified:
                    staff_user = self._matching_staff_user(email_address.email)
                    if staff_user:
                        return staff_user, email_address.email
        return super().authenticate_by_email(sociallogin)

    def pre_social_login(self, request, sociallogin):
        if sociallogin.provider.id != 'google' or not sociallogin.account.pk:
            return

        for email_address in sociallogin.email_addresses:
            if not email_address.verified:
                continue
            staff_user = self._matching_staff_user(email_address.email)
            if staff_user and sociallogin.account.user_id != staff_user.pk:
                sociallogin.account.user = staff_user
                sociallogin.account.save(update_fields=['user'])
                sociallogin.user = staff_user
                return
