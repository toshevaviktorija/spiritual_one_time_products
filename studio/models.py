import uuid
from django.db import models
from .validators import validate_public_email

class Enquiry(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(validators=[validate_public_email])
    message = models.TextField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "enquiries"

    def __str__(self):
        return self.name

class Report(models.Model):
    birth_request = models.ForeignKey("BirthRequest", null=True, blank=True, on_delete=models.SET_NULL, related_name="reports")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

class BirthRequest(models.Model):
    delivery_consent = models.JSONField(default=dict, editable=False)
    payment_mode = models.CharField(max_length=8, default="test", choices=[("demo", "Local demo"), ("test", "Stripe test"), ("live", "Live payment")])
    removal_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'Submitted (payments disabled)'
        PENDING = 'pending', 'Awaiting payment'
        PAID = 'paid', 'Paid'
        FREE = 'free', 'Free redemption'

    class Source(models.TextChoices):
        STOREFRONT = 'storefront', 'Storefront'
        PROMOTION = 'promotion', 'Free promotion'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payload = models.JSONField()
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.STOREFRONT)
    report_sent = models.BooleanField(default=False, help_text='Mark this after manually emailing the report.')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    amount_pence = models.PositiveIntegerField(default=3900, editable=False)
    currency = models.CharField(max_length=3, default='gbp', editable=False)
    stripe_session_id = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)
    email = models.EmailField(blank=True, validators=[validate_public_email])
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.payload.get('name', str(self.id))


from django.core.validators import MinValueValidator, MaxValueValidator

class Review(models.Model):
    birth_request = models.ForeignKey(BirthRequest, null=True, blank=True, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(max_length=2000)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name='review_rating_1_to_5')]

    @property
    def stars(self):
        return '★' * self.rating + '☆' * (5 - self.rating)

    def __str__(self):
        return f'{self.rating}-star review'

class Feedback(models.Model):
    birth_request = models.ForeignKey(BirthRequest, null=True, blank=True, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(max_length=2000)
    reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'private feedback'
        constraints = [models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name='feedback_rating_1_to_5')]

    def __str__(self):
        return 'Private feedback'


class ChartEmail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    birth_request = models.ForeignKey(BirthRequest, on_delete=models.PROTECT, related_name='chart_emails')
    report = models.ForeignKey(Report, on_delete=models.PROTECT)
    recipient = models.EmailField(validators=[validate_public_email])
    sender = models.EmailField(validators=[validate_public_email])
    reply_to = models.EmailField(blank=True, validators=[validate_public_email])
    subject = models.CharField(max_length=200)
    message = models.TextField()
    pdf_sha256 = models.CharField(max_length=64)
    provider_id = models.CharField(max_length=255, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.PROTECT)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.subject} → {self.recipient}'


class DataRemovalRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    birth_request = models.ForeignKey(BirthRequest, null=True, on_delete=models.SET_NULL)
    email = models.EmailField()
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return self.email or 'Completed data removal'


class Invoice(models.Model):
    line_items = models.JSONField(default=list)
    birth_request = models.OneToOneField(BirthRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name='invoice')
    contract_terms = models.JSONField(default=dict)
    payment_reference = models.CharField(max_length=255, blank=True)
    issued_at = models.DateTimeField()
    customer = models.JSONField()
    issuer = models.JSONField()
    total_pence = models.PositiveIntegerField()
    vat_pence = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default='gbp')
    is_test = models.BooleanField(default=True)

    @property
    def number(self):
        prefix = 'TEST' if self.is_test else 'VEN'
        return f'{prefix}-{self.issued_at.year}-{self.pk:06d}'

    def __str__(self):
        return self.number
