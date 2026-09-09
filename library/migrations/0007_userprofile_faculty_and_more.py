# Generated manually to match project migration style (Django 5.2.11)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('library', '0006_otpverification'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='faculty',
            field=models.CharField(
                blank=True,
                choices=[
                    ('computer_engineering', 'Faculty of Computer Engineering'),
                    ('computing_information_systems', 'Faculty of Computing and Information Systems'),
                    ('business_school', 'GCTU Business School'),
                ],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='phone_number',
            field=models.CharField(blank=True, max_length=15, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='borrowing',
            name='admin_note',
            field=models.CharField(
                blank=True,
                help_text='Optional note left by the librarian when approving/rejecting.',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='borrowing',
            name='fine_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
    ]
