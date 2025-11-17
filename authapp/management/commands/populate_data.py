from django.core.management.base import BaseCommand
from authapp.models import Survey

class Command(BaseCommand):
    def handle(self, *args, **options):
        surveys = [
            {
                'title': 'Mobile Banking App Experience',
                'description': 'Share your experience with mobile banking apps in Kenya',
                'reward_amount': 200.00,
                'estimated_time': 8,
                'category': 'finance',
                'difficulty': 'medium',
                'questions_count': 12,
                'is_premium_only': False
            },
            {
                'title': 'Consumer Preferences - Soft Drinks',
                'description': 'Tell us about your soft drink preferences and buying habits',
                'reward_amount': 150.00,
                'estimated_time': 5,
                'category': 'consumer',
                'difficulty': 'easy',
                'questions_count': 8,
                'is_premium_only': False
            },
            {
                'title': 'Premium: Luxury Car Brands Survey',
                'description': 'Exclusive survey about luxury car brand preferences',
                'reward_amount': 500.00,
                'estimated_time': 12,
                'category': 'automotive',
                'difficulty': 'premium',
                'questions_count': 15,
                'is_premium_only': True
            },
        ]
        
        for survey_data in surveys:
            Survey.objects.create(**survey_data)
        
        self.stdout.write(
            self.style.SUCCESS('Successfully created 3 sample surveys!')
        )