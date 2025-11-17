# authapp/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import CustomUser, Survey, UserSurvey, Transaction

def format_phone_number(phone_number):
    """Helper function to format phone number consistently with CustomUserManager"""
    if not phone_number:
        return phone_number
    
    # Use the same normalization as in CustomUserManager
    from .models import CustomUser
    try:
        return CustomUser.objects.normalize_phone_number(phone_number)
    except:
        # Fallback formatting if manager method fails
        phone_number = str(phone_number).strip()
        
        # Remove any spaces, dashes, etc.
        import re
        phone_number = re.sub(r'[^\d+]', '', phone_number)
        
        # If it starts with 0, replace with +254
        if phone_number.startswith('0'):
            phone_number = '+254' + phone_number[1:]
        # If it starts with 7 or 1 (without country code), add +254
        elif phone_number.startswith('7') or phone_number.startswith('1'):
            phone_number = '+254' + phone_number
        # If it already has +254, leave as is
        elif phone_number.startswith('+254'):
            pass
        
        return phone_number

# Simple Registration
@csrf_exempt
def register_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            phone_number = data.get('phoneNumber')
            pin = data.get('pin')
            confirm_pin = data.get('confirmPin')
            
            print(f"📝 Registration attempt - Raw phone: {phone_number}, PIN: {pin}")  # Debug
            
            # Basic validation
            if pin != confirm_pin:
                return JsonResponse({'success': False, 'message': 'PINs do not match'})
            
            if len(pin) != 4 or not pin.isdigit():
                return JsonResponse({'success': False, 'message': 'PIN must be 4 digits'})
            
            # Create user using the manager (it handles phone formatting and PIN hashing)
            user = CustomUser.objects.create_user(
                phone_number=phone_number,
                pin=pin
            )
            
            print(f"📝 User created successfully: {user.phone_number}")  # Debug
            print(f"📝 User PIN hash: {user.pin}")  # Debug
            print(f"📝 PIN check test: {user.check_pin(pin)}")  # Debug
            
            # Auto-login after registration
            login(request, user, backend='authapp.backends.PhoneAuthBackend')
            
            return JsonResponse({
                'success': True,
                'message': 'Registration successful! Ksh 500 bonus credited.',
                'redirect_url': '/auth/dashboard/'
            })
            
        except ValueError as e:
            # Handle validation errors from the manager
            return JsonResponse({'success': False, 'message': str(e)})
        except Exception as e:
            print(f"📝 Registration error: {e}")  # Debug
            return JsonResponse({'success': False, 'message': 'Registration failed. Please try again.'})
    
    return render(request, 'register.html')

# Simple Login
@csrf_exempt
def login_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            phone_number = data.get('phoneNumber')
            pin = data.get('pin')
            
            print(f"🔐 Login attempt - Raw phone: {phone_number}, PIN: {pin}")  # Debug
            
            # Format phone number consistently using the same method as registration
            formatted_phone = format_phone_number(phone_number)
            print(f"🔐 Formatted phone: {formatted_phone}")  # Debug
            
            # Debug: Check what users exist with this phone
            matching_users = CustomUser.objects.filter(phone_number=formatted_phone)
            print(f"🔐 Matching users found: {matching_users.count()}")  # Debug
            
            if matching_users.exists():
                user = matching_users.first()
                print(f"🔐 Found user: {user.phone_number}")  # Debug
                print(f"🔐 User PIN hash: {user.pin}")  # Debug
                print(f"🔐 Direct PIN check: {user.check_pin(pin)}")  # Debug
            
            # Authenticate user
            user = authenticate(request, phone_number=formatted_phone, pin=pin)
            
            print(f"🔐 Authentication result: {user}")  # Debug
            
            if user is not None:
                login(request, user)
                return JsonResponse({
                    'success': True, 
                    'message': 'Login successful!',
                    'redirect_url': '/auth/dashboard/'
                })
            else:
                # More detailed error information
                try:
                    user_exists = CustomUser.objects.filter(phone_number=formatted_phone).exists()
                    print(f"🔐 User exists: {user_exists}")  # Debug
                    
                    if user_exists:
                        # Test PIN directly
                        test_user = CustomUser.objects.get(phone_number=formatted_phone)
                        pin_valid = test_user.check_pin(pin)
                        print(f"🔐 Direct PIN validation: {pin_valid}")  # Debug
                        
                        if not pin_valid:
                            return JsonResponse({
                                'success': False, 
                                'message': 'Invalid PIN. Please try again.'
                            })
                        else:
                            return JsonResponse({
                                'success': False, 
                                'message': 'Authentication failed. Please try again.'
                            })
                    else:
                        return JsonResponse({
                            'success': False, 
                            'message': 'Phone number not registered. Please sign up first.'
                        })
                except Exception as debug_error:
                    print(f"🔐 Debug error: {debug_error}")  # Debug
                    return JsonResponse({
                        'success': False, 
                        'message': 'Invalid phone number or PIN'
                    })
                
        except Exception as e:
            print(f"🔐 Login error: {e}")  # Debug
            return JsonResponse({
                'success': False, 
                'message': 'An error occurred. Please try again.'
            })
    
    return render(request, 'login.html')

# Logout
def logout_view(request):
    logout(request)
    return redirect('/')

# Simple Dashboard
@login_required
def dashboard_view(request):
    user = request.user
    
    # Get available surveys (only show if user is premium)
    if user.is_premium:
        available_surveys = Survey.objects.filter(
            is_active=True
        ).exclude(
            usersurvey__user=user,
            usersurvey__status__in=['started', 'completed']
        )[:5]
    else:
        available_surveys = []
    
    # Get user stats
    completed_surveys = UserSurvey.objects.filter(user=user, status='completed').count()
    total_earnings = user.total_earned
    current_balance = user.balance
    
    context = {
        'user': user,
        'available_surveys': available_surveys,
        'completed_surveys': completed_surveys,
        'total_earnings': total_earnings,
        'current_balance': current_balance,
        'is_premium': user.is_premium,
    }
    
    return render(request, 'dashboard.html', context)

# Premium Activation
@login_required
@csrf_exempt
def activate_premium_view(request):
    if request.method == 'POST':
        user = request.user
        
        if user.is_premium:
            return JsonResponse({
                'success': False,
                'message': 'You are already a premium member!'
            })
        
        # Activate premium (for now, just toggle - later integrate payment)
        user.activate_premium()
        
        return JsonResponse({
            'success': True,
            'message': 'Premium membership activated successfully! You now have access to premium surveys.',
            'redirect_url': '/auth/dashboard/'
        })
    
    return render(request, 'activate_premium.html')

# Debug view to check stored users
@csrf_exempt
def debug_users(request):
    """Temporary view to debug user data"""
    users = CustomUser.objects.all()
    user_data = []
    for user in users:
        user_data.append({
            'id': user.id,
            'phone_number': user.phone_number,
            'has_pin': bool(user.pin),
            'pin_hash': user.pin[:50] + '...' if len(user.pin) > 50 else user.pin,
            'is_premium': user.is_premium,
            'balance': float(user.balance),
            'is_active': user.is_active
        })
    return JsonResponse({'users': user_data})

# Test PIN verification
@csrf_exempt
def test_pin_verification(request):
    """Test PIN verification for debugging"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            phone_number = data.get('phoneNumber')
            pin = data.get('pin')
            
            formatted_phone = format_phone_number(phone_number)
            
            user = CustomUser.objects.get(phone_number=formatted_phone)
            
            # Test different authentication methods
            backend_auth = authenticate(request, phone_number=formatted_phone, pin=pin)
            direct_check = user.check_pin(pin)
            
            return JsonResponse({
                'user_found': True,
                'phone_number': user.phone_number,
                'direct_pin_check': direct_check,
                'backend_authentication': backend_auth is not None,
                'backend_user': str(backend_auth) if backend_auth else None,
                'pin_hash_length': len(user.pin),
                'user_is_active': user.is_active
            })
            
        except CustomUser.DoesNotExist:
            return JsonResponse({'user_found': False, 'error': 'User not found'})
        except Exception as e:
            return JsonResponse({'error': str(e)})
    
    return JsonResponse({'message': 'Send POST request with phoneNumber and pin'})