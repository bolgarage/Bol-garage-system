from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .notifications import send_welcome_email

LOGO_PATH = Path(__file__).parent / 'static' / 'media' / 'BG logo.png'


class InlineLogoEmailMultiAlternatives(EmailMultiAlternatives):
    def __init__(self, *args, logo_content, **kwargs):
        super().__init__(*args, **kwargs)
        self.logo_content = logo_content

    def message(self, *, policy=None):
        if policy is None:
            message = super().message()
        else:
            message = super().message(policy=policy)

        html_body = next(
            (
                part
                for part in message.walk()
                if part.get_content_type() == 'text/html' and not part.is_multipart()
            ),
            None,
        )
        if html_body is None:
            raise ValueError('The password-reset email has no HTML body for its inline logo.')

        html_body.add_related(
            self.logo_content,
            maintype='image',
            subtype='png',
            cid='<bol-garage-logo>',
            disposition='inline',
            filename='bol-garage-logo.png',
        )
        return message


class GarageAccountAdapter(DefaultAccountAdapter):
    def render_mail(self, template_prefix, email, context, headers=None):
        message = super().render_mail(template_prefix, email, context, headers)
        if template_prefix == 'account/email/password_reset_key':
            if not isinstance(message, EmailMultiAlternatives):
                raise TypeError('The password-reset email must support HTML alternatives.')

            inline_message = InlineLogoEmailMultiAlternatives(
                message.subject,
                message.body,
                message.from_email,
                message.to,
                bcc=message.bcc,
                connection=message.connection,
                headers=message.extra_headers,
                cc=message.cc,
                reply_to=message.reply_to,
                logo_content=LOGO_PATH.read_bytes(),
            )
            inline_message.alternatives = message.alternatives
            inline_message.attachments = message.attachments
            inline_message.encoding = message.encoding
            return inline_message
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
