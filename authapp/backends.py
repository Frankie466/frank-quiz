# authapp/backends.py
from django.contrib.auth.backends import BaseBackend
from .models import CustomUser

class PhoneAuthBackend(BaseBackend):
    def authenticate(self, request, phone_number=None, pin=None, **kwargs):
        try:
            print(f"🔑 Backend authentication attempt - Phone: {phone_number}, PIN: {pin}")
            
            # Use the same phone normalization as the manager
            formatted_phone = CustomUser.objects.normalize_phone_number(phone_number)
            print(f"🔑 Backend formatted phone: {formatted_phone}")
            
            user = CustomUser.objects.get(phone_number=formatted_phone)
            print(f"🔑 Backend found user: {user.phone_number}")
            
            if user.check_pin(pin):
                print(f"🔑 Backend PIN validation SUCCESS")
                return user
            else:
                print(f"🔑 Backend PIN validation FAILED")
                return None
                
        except CustomUser.DoesNotExist:
            print(f"🔑 Backend user not found: {formatted_phone}")
            return None
        except Exception as e:
            print(f"🔑 Backend error: {e}")
            return None
    
    def get_user(self, user_id):
        try:
            return CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            return None