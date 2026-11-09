from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Profile, User


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={'phone_number': instance.phone},
        )


@receiver(pre_save, sender=Profile)
def remember_previous_avatar(sender, instance, **kwargs):
    instance._previous_avatar_name = None
    if instance.pk:
        instance._previous_avatar_name = (
            sender.objects.filter(pk=instance.pk)
            .values_list('avatar', flat=True)
            .first()
        )


@receiver(post_save, sender=Profile)
def delete_replaced_avatar(sender, instance, **kwargs):
    previous_name = getattr(instance, '_previous_avatar_name', None)
    current_name = instance.avatar.name if instance.avatar else None
    if previous_name and previous_name != current_name:
        sender._meta.get_field('avatar').storage.delete(previous_name)


@receiver(post_delete, sender=Profile)
def delete_profile_avatar(sender, instance, **kwargs):
    if instance.avatar:
        instance.avatar.storage.delete(instance.avatar.name)
