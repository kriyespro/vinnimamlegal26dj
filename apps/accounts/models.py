from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", User.Role.CLIENT)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=User.Role.CEO)
        return self._create(email, password, **extra)


class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = "client", "Client"
        PARTNER = "partner", "Partner / Advocate"
        STAFF = "staff", "Office staff"
        CEO = "ceo", "Founder / CEO"

    username = None
    first_name = None
    last_name = None
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CLIENT)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]
    objects = UserManager()

    def __str__(self):
        return f"{self.name} <{self.email}>"

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.name.split()[0] if self.name else self.email

    class Meta(AbstractUser.Meta):
        indexes = [
            models.Index(fields=["role", "is_active"], name="user_role_active"),
        ]


class PolicyAcceptance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="policy_acceptances")
    version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "version"], name="uniq_policy_per_version")]
