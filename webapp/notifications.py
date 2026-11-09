from email.message import MIMEPart
import logging
import smtplib
from email.utils import formataddr, parseaddr
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, mailers
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

LOGO_PATH = Path(__file__).parent / 'static' / 'media' / 'BG logo.png'


def _send_branded_email(subject, body, recipient, template, context, email_kind):
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        logger.error(
            '%s email was not sent because SMTP credentials are not configured.',
            email_kind,
        )
        return False

    if not recipient:
        logger.error('%s email was not sent because the recipient address is empty.', email_kind)
        return False

    sender_address = (
        parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
        or settings.SMTP_USERNAME
        or settings.CONTACT_NOTIFICATION_EMAIL
    )
    try:
        logo_content = LOGO_PATH.read_bytes()
    except OSError:
        logger.exception('Could not read the BOL Garage %s email logo.', email_kind.lower())
        return False

    email = EmailMultiAlternatives(
        subject,
        body,
        formataddr((settings.EMAIL_SENDER_NAME, sender_address)),
        [recipient],
    )
    email.attach_alternative(
        render_to_string(template, context),
        'text/html',
    )
    logo = MIMEPart()
    logo.set_content(
        logo_content,
        maintype='image',
        subtype='png',
        cid='<bol-garage-logo>',
        disposition='inline',
        filename='bol-garage-logo.png',
    )
    email.attach(logo)

    try:
        sent_count = mailers['default'].send_messages([email])
    except (OSError, smtplib.SMTPException):
        logger.exception('Could not send BOL Garage %s email.', email_kind.lower())
        return False

    if sent_count != 1:
        logger.error('%s email was not accepted by the email backend.', email_kind)
        return False
    return True


def send_admin_notification(subject, body):
    return _send_branded_email(
        subject,
        body,
        settings.CONTACT_NOTIFICATION_EMAIL,
        'emails/admin_notification.html',
        {'subject': subject, 'body': body},
        'Admin notification',
    )


def send_welcome_email(user):
    name = user.first_name or user.get_username()
    subject = 'Welcome to BOL Garage'
    body = (
        f'Hi {name},\n\n'
        'Welcome to BOL Garage. Your account is ready, and you can now send '
        'inquiries, ask to reserve a car, and follow your requests.\n\n'
        'Thank you for joining us,\n'
        'The BOL Garage team'
    )
    return _send_branded_email(
        subject,
        body,
        user.email,
        'emails/welcome.html',
        {'name': name},
        'Welcome',
    )


def send_inactivity_warning(user, inactive_days, login_url):
    name = user.first_name or user.get_username()
    subject = f'BOL Garage account inactivity reminder ({inactive_days} days)'
    body = (
        f'Hi {name},\n\n'
        f'Your BOL Garage account has been inactive for {inactive_days} days. '
        'Sign in to keep your account active. Accounts with 120 days of '
        'inactivity are deactivated automatically.\n\n'
        f'Sign in: {login_url}\n\n'
        'If you have already signed in, you can ignore this reminder.'
    )
    return _send_branded_email(
        subject,
        body,
        user.email,
        'emails/inactivity_warning.html',
        {
            'name': name,
            'inactive_days': inactive_days,
            'login_url': login_url,
        },
        'Inactivity reminder',
    )
