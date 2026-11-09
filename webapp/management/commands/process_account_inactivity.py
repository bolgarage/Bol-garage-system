from datetime import timedelta

from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from webapp.models import User
from webapp.notifications import send_inactivity_warning


class Command(BaseCommand):
    help = (
        'Send account inactivity reminders at 60 and 90 days, and deactivate '
        'regular accounts after 120 days.'
    )

    def handle(self, *args, **options):
        now = timezone.now()
        protocol = 'http' if settings.DEBUG else 'https'
        domain = get_current_site(None).domain
        login_url = f'{protocol}://{domain}{reverse("webapp:sign_in")}'
        warned = 0
        deactivated = 0
        failed = 0

        accounts = User.objects.filter(
            role='buyer',
            is_active=True,
            is_staff=False,
            is_superuser=False,
        ).order_by('pk')

        for account in accounts.iterator():
            activity_anchor = max(
                account.date_joined,
                account.inactivity_reset_at,
                account.last_login or account.date_joined,
            )
            inactive_for = now - activity_anchor

            if inactive_for >= timedelta(days=120):
                account.is_active = False
                account.save(update_fields=['is_active'])
                deactivated += 1
                continue

            if inactive_for >= timedelta(days=90):
                if account.inactivity_warning_90_sent_for == activity_anchor:
                    continue
                if send_inactivity_warning(account, 90, login_url):
                    account.inactivity_warning_60_sent_for = activity_anchor
                    account.inactivity_warning_90_sent_for = activity_anchor
                    account.save(update_fields=[
                        'inactivity_warning_60_sent_for',
                        'inactivity_warning_90_sent_for',
                    ])
                    warned += 1
                else:
                    failed += 1
            elif inactive_for >= timedelta(days=60):
                if account.inactivity_warning_60_sent_for == activity_anchor:
                    continue
                if send_inactivity_warning(account, 60, login_url):
                    account.inactivity_warning_60_sent_for = activity_anchor
                    account.save(update_fields=['inactivity_warning_60_sent_for'])
                    warned += 1
                else:
                    failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Inactivity policy processed: {warned} reminder(s) sent, '
                f'{deactivated} account(s) deactivated.'
            )
        )
        if failed:
            self.stderr.write(
                self.style.WARNING(
                    f'{failed} reminder(s) failed and will be retried on the next run.'
                )
            )
