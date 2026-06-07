from django.db import models
from accounts.models import Company


STATUS_CHOICES = [
    ('processing',  'En cours'),
    ('validated',   'Validée'),
    ('rejected',    'Rejetée (DiT)'),
    ('need_review', 'À réviser'),
]

CATEGORY_CHOICES = [
    ('SaaS',                       'SaaS'),
    ('Travel',                     'Voyage'),
    ('Office',                     'Bureau'),
    ('Utilities',                  'Charges'),
    ('IT Hardware',                'Matériel IT'),
    ('Consulting & Services',      'Consulting'),
    ('Marketing & Communication',  'Marketing'),
    ('Legal & Compliance',         'Juridique'),
    ('Maintenance & Repair',       'Maintenance'),
    ('Other',                      'Autre'),
]


class InvoiceRecord(models.Model):
    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='invoices')

    # Extracted fields
    vendor_name      = models.CharField(max_length=200, blank=True)
    invoice_date     = models.CharField(max_length=20,  blank=True)
    invoice_id       = models.CharField(max_length=100, blank=True)
    total_amount     = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    subtotal         = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    tax_amount       = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency         = models.CharField(max_length=10, blank=True, default='MAD')
    expense_category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, blank=True)

    # DiT fields
    dit_confidence   = models.FloatField(null=True, blank=True)
    dit_label        = models.CharField(max_length=20, blank=True)
    dit_is_invoice   = models.BooleanField(null=True)

    # LLM
    llm_confidence   = models.CharField(max_length=10, blank=True)

    # Validation
    is_valid              = models.BooleanField(default=False)
    validation_errors     = models.JSONField(default=list, blank=True)
    validation_warnings   = models.JSONField(default=list, blank=True)
    attempt_count         = models.IntegerField(default=1)

    # Pipeline
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing')
    source_filename  = models.CharField(max_length=255, blank=True)
    source           = models.CharField(max_length=20, default='email',
                                        help_text='email | upload')
    content_hash     = models.CharField(max_length=32, blank=True, db_index=True,
                                        help_text='MD5 du fichier — évite les doublons')

    # Excel report
    excel_file       = models.FileField(upload_to='excel_reports/', null=True, blank=True)

    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering             = ['-created_at']
        verbose_name         = 'Facture'
        verbose_name_plural  = 'Factures'

    def __str__(self):
        return f"{self.vendor_name or 'Inconnu'} | {self.invoice_date} | {self.total_amount} {self.currency}"
