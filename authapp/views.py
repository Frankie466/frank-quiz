# authapp/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import requests
import base64
from datetime import datetime
import logging
from .models import CustomUser, Survey, UserSurvey, Transaction, MpesaTransaction

logger = logging.getLogger(__name__)

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

# M-Pesa Gateway Class
class MpesaGateway:
    def __init__(self):
        # PRODUCTION CREDENTIALS
        self.consumer_key = '0VxpuiMStrKodudK2das68bxDGW7GduDHaAuLYJarUn0VJ8d'
        self.consumer_secret = 'ji9gGA0u4aGH66wsqJaBEJ2rVn8wWNNfcUVthP65frDwMSkKSjIvhvAcdx0wU3p6'
        self.shortcode = '5515540'  # Your production till number
        self.passkey = '9d1c2d098353f5790d13f2faca56ebc8ff4c98e5970f307908e19f04e38ce54c'
        
        # IMPORTANT: Update this to your actual production domain
        # This should be HTTPS and publicly accessible
        self.callback_url = 'https://starrlnk.shop/auth/mpesa-callback/'
        
        # Production URLs
        self.auth_url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        self.stk_push_url = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        
        logger.info(f"M-Pesa Gateway initialized with shortcode: {self.shortcode}")
    
    def get_access_token(self):
        """Get Daraja API access token for production"""
        try:
            auth = (self.consumer_key, self.consumer_secret)
            response = requests.get(self.auth_url, auth=auth, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get('access_token')
                if access_token:
                    logger.info("Successfully obtained production access token")
                    return access_token
                else:
                    logger.error("No access_token in response")
                    return None
            else:
                logger.error(f"Failed to get access token: Status {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None
        except requests.exceptions.Timeout:
            logger.error("Access token request timeout")
            return None
        except Exception as e:
            logger.error(f"Error getting access token: {str(e)}")
            return None
    
    def get_timestamp(self):
        """Get current timestamp in required format"""
        return datetime.now().strftime('%Y%m%d%H%M%S')
    
    def generate_password(self, timestamp):
        """Generate Daraja API password"""
        data_to_encode = f"{self.shortcode}{self.passkey}{timestamp}"
        encoded_string = base64.b64encode(data_to_encode.encode()).decode()
        return encoded_string
    
    def initiate_stk_push(self, phone_number, amount, account_reference, transaction_desc):
        """Initiate STK Push payment in production"""
        try:
            access_token = self.get_access_token()
            if not access_token:
                logger.error("Failed to obtain access token")
                return None, "Payment service temporarily unavailable. Please try again in a few minutes."
            
            timestamp = self.get_timestamp()
            password = self.generate_password(timestamp)
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Format phone number for M-Pesa (254XXXXXXXXX)
            phone_number = str(phone_number).strip()
            
            # Remove + if present
            if phone_number.startswith('+'):
                phone_number = phone_number[1:]
            
            # Ensure it's 12 digits starting with 254
            if phone_number.startswith('0'):
                phone_number = '254' + phone_number[1:]
            elif phone_number.startswith('7') and len(phone_number) == 9:
                phone_number = '254' + phone_number
            elif phone_number.startswith('254'):
                phone_number = phone_number
            else:
                return None, "Invalid phone number format. Please use format: 7XXXXXXXX"
            
            # Validate phone number length
            if len(phone_number) != 12:
                return None, "Phone number must be 12 digits (254XXXXXXXXX)"
            
            # Validate amount
            try:
                amount = int(amount)
                if amount <= 0:
                    return None, "Invalid amount"
            except:
                return None, "Invalid amount"
            
            # Prepare payload for PRODUCTION
            payload = {
                "BusinessShortCode": self.shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerBuyGoodsOnline",  # For Till
                "Amount": amount,
                "PartyA": phone_number,
                "PartyB": 4160709,
                "PhoneNumber": phone_number,
                "CallBackURL": self.callback_url,
                "AccountReference": account_reference[:12],  # Max 12 chars
                "TransactionDesc": transaction_desc[:13]  # Max 13 chars
            }
            
            logger.info(f"Production STK Push payload for {phone_number}: Amount {amount}")
            
            # Make production API call
            response = requests.post(
                self.stk_push_url, 
                json=payload, 
                headers=headers, 
                timeout=30
            )
            
            logger.info(f"STK Push response status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"STK Push response data: {response_data}")
                
                if response_data.get('ResponseCode') == '0':
                    logger.info(f"STK Push initiated successfully. MerchantRequestID: {response_data.get('MerchantRequestID')}")
                    return response_data, None
                else:
                    error_code = response_data.get('ResponseCode')
                    error_msg = response_data.get('CustomerMessage', 'Payment initiation failed')
                    logger.error(f"STK Push failed with code {error_code}: {error_msg}")
                    
                    # User-friendly error messages
                    if error_code == '1032':
                        return None, "Request cancelled by user"
                    elif error_code == '1037':
                        return None, "Timeout - please try again"
                    elif error_code == '1':
                        return None, "Insufficient M-Pesa balance"
                    elif error_code == '2001':
                        return None, "Transaction declined"
                    else:
                        return None, f"Payment failed: {error_msg}"
            else:
                error_msg = f"API Error: Status {response.status_code}"
                logger.error(f"{error_msg}. Response: {response.text}")
                return None, "Payment service error. Please try again."
                
        except requests.exceptions.Timeout:
            logger.error("STK Push request timeout")
            return None, "Request timeout. Please try again."
        except requests.exceptions.ConnectionError:
            logger.error("STK Push connection error")
            return None, "Network error. Please check your connection and try again."
        except Exception as e:
            logger.error(f"Unexpected error in STK Push: {str(e)}")
            return None, "An unexpected error occurred. Please try again."

# Simple Registration
@csrf_exempt
def register_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            phone_number = data.get('phoneNumber')
            pin = data.get('pin')
            confirm_pin = data.get('confirmPin')
            
            logger.info(f"Registration attempt - Phone: {phone_number}")
            
            # Basic validation
            if pin != confirm_pin:
                return JsonResponse({'success': False, 'message': 'PINs do not match'})
            
            if len(pin) != 4 or not pin.isdigit():
                return JsonResponse({'success': False, 'message': 'PIN must be 4 digits'})
            
            # Create user using the manager
            user = CustomUser.objects.create_user(
                phone_number=phone_number,
                pin=pin
            )
            
            logger.info(f"User created successfully: {user.phone_number}")
            
            # Auto-login after registration
            login(request, user, backend='authapp.backends.PhoneAuthBackend')
            
            return JsonResponse({
                'success': True,
                'message': 'Registration successful! Ksh 500 bonus credited.',
                'redirect_url': '/auth/dashboard/'
            })
            
        except ValueError as e:
            return JsonResponse({'success': False, 'message': str(e)})
        except Exception as e:
            logger.error(f"Registration error: {e}")
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
            
            logger.info(f"Login attempt - Phone: {phone_number}")
            
            # Format phone number consistently
            formatted_phone = format_phone_number(phone_number)
            
            # Authenticate user
            user = authenticate(request, phone_number=formatted_phone, pin=pin)
            
            if user is not None:
                login(request, user)
                logger.info(f"Login successful: {user.phone_number}")
                return JsonResponse({
                    'success': True, 
                    'message': 'Login successful!',
                    'redirect_url': '/auth/dashboard/'
                })
            else:
                try:
                    user_exists = CustomUser.objects.filter(phone_number=formatted_phone).exists()
                    
                    if user_exists:
                        return JsonResponse({
                            'success': False, 
                            'message': 'Invalid PIN. Please try again.'
                        })
                    else:
                        return JsonResponse({
                            'success': False, 
                            'message': 'Phone number not registered. Please sign up first.'
                        })
                except Exception:
                    return JsonResponse({
                        'success': False, 
                        'message': 'Invalid phone number or PIN'
                    })
                
        except Exception as e:
            logger.error(f"Login error: {e}")
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

# Premium Activation Page
@login_required
def activate_premium_view(request):
    return render(request, 'activate_premium.html')

# Initiate M-Pesa Payment
@login_required
@csrf_exempt
def initiate_premium_payment(request):
    """Initiate M-Pesa STK Push for premium activation"""
    if request.method == 'POST':
        try:
            user = request.user
            
            if user.is_premium:
                return JsonResponse({
                    'success': False,
                    'message': 'You are already a premium member!'
                })
            
            data = json.loads(request.body)
            phone_number = data.get('phone_number')
            
            if not phone_number:
                return JsonResponse({
                    'success': False,
                    'message': 'Phone number is required'
                })
            
            # Amount for premium activation
            amount = 79
            
            # Generate unique reference
            import time
            timestamp = int(time.time())
            account_reference = f"PREMIUM{user.id}"
            transaction_desc = f"Premium Activation"
            
            # Initialize M-Pesa gateway
            mpesa = MpesaGateway()
            
            # Log the attempt
            logger.info(f"Production payment initiation for user {user.id}, phone: {phone_number}")
            
            # Initiate STK Push
            response, error = mpesa.initiate_stk_push(
                phone_number=phone_number,
                amount=amount,
                account_reference=account_reference,
                transaction_desc=transaction_desc
            )
            
            if error:
                logger.error(f"Production STK Push failed: {error}")
                return JsonResponse({
                    'success': False,
                    'message': error
                }, status=400)
            
            # Save transaction to database
            transaction = MpesaTransaction.objects.create(
                user=user,
                phone_number=phone_number,
                amount=amount,
                checkout_request_id=response.get('CheckoutRequestID'),
                merchant_request_id=response.get('MerchantRequestID'),
                account_reference=account_reference,
                transaction_desc=transaction_desc,
                status='PENDING'
            )
            
            logger.info(f"Production payment initiated successfully: CheckoutID: {response.get('CheckoutRequestID')}")
            
            return JsonResponse({
                'success': True,
                'message': 'Payment initiated successfully. Check your phone to enter M-Pesa PIN.',
                'checkout_request_id': response.get('CheckoutRequestID'),
                'transaction_id': transaction.id,
                'merchant_request_id': response.get('MerchantRequestID')
            })
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON in payment request")
            return JsonResponse({
                'success': False,
                'message': 'Invalid request data'
            }, status=400)
        except Exception as e:
            logger.error(f"Payment initiation error: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': 'An error occurred. Please try again.'
            }, status=500)
    
    return JsonResponse({
        'success': False,
        'message': 'Invalid request method'
    }, status=405)

# M-Pesa Callback Handler
@csrf_exempt
def mpesa_callback(request):
    """Handle Daraja API callback for payment confirmation in production"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info(f"Production callback received: {data}")
            
            callback_data = data.get('Body', {}).get('stkCallback', {})
            
            checkout_request_id = callback_data.get('CheckoutRequestID')
            result_code = callback_data.get('ResultCode')
            result_desc = callback_data.get('ResultDesc')
            
            logger.info(f"Production callback - CheckoutID: {checkout_request_id}, Result: {result_code}")
            
            # Find transaction
            try:
                transaction = MpesaTransaction.objects.get(
                    checkout_request_id=checkout_request_id
                )
                
                logger.info(f"Found production transaction for user: {transaction.user.id}")
                
                if result_code == 0:
                    # Payment successful
                    transaction.status = 'COMPLETED'
                    transaction.result_code = result_code
                    transaction.result_desc = result_desc
                    
                    # Extract M-Pesa receipt details
                    callback_metadata = callback_data.get('CallbackMetadata', {}).get('Item', [])
                    receipt_number = None
                    for item in callback_metadata:
                        if item.get('Name') == 'MpesaReceiptNumber':
                            receipt_number = item.get('Value')
                            transaction.mpesa_receipt = receipt_number
                        elif item.get('Name') == 'PhoneNumber':
                            transaction.phone_number = item.get('Value')
                        elif item.get('Name') == 'Amount':
                            transaction.amount = item.get('Value')
                        elif item.get('Name') == 'TransactionDate':
                            transaction.transaction_date = item.get('Value')
                    
                    transaction.save()
                    
                    # Activate premium for user
                    user = transaction.user
                    if not user.is_premium:
                        logger.info(f"Activating premium for user in production: {user.id}")
                        user.activate_premium()
                        user.save()
                        
                        logger.info(f"Production premium activated for user: {user.username}")
                    
                    logger.info(f"Production payment completed. Receipt: {receipt_number}")
                    
                else:
                    # Payment failed
                    transaction.status = 'FAILED'
                    transaction.result_code = result_code
                    transaction.result_desc = result_desc
                    transaction.save()
                    
                    logger.warning(f"Production payment failed for user: {transaction.user.username}, Reason: {result_desc}")
                
            except MpesaTransaction.DoesNotExist:
                logger.error(f"Production transaction not found: {checkout_request_id}")
            except Exception as e:
                logger.error(f"Error processing production callback: {str(e)}")
            
            # Always return success to Daraja API
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid callback JSON in production: {str(e)}")
            return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Production callback error: {str(e)}")
            return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Server error'}, status=500)
    
    return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid method'}, status=405)

# Check Payment Status
@login_required
@csrf_exempt
def check_payment_status(request):
    """Check payment status for a transaction"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            checkout_request_id = data.get('checkout_request_id')
            
            if not checkout_request_id:
                return JsonResponse({
                    'success': False,
                    'message': 'Transaction ID is required'
                })
            
            try:
                transaction = MpesaTransaction.objects.get(
                    checkout_request_id=checkout_request_id,
                    user=request.user
                )
                
                # Check if user is already premium (in case callback was successful)
                if request.user.is_premium:
                    return JsonResponse({
                        'success': True,
                        'status': 'COMPLETED',
                        'premium_active': True,
                        'message': 'Premium membership is active!',
                        'redirect_url': '/auth/dashboard/'
                    })
                
                return JsonResponse({
                    'success': True,
                    'status': transaction.status,
                    'premium_active': False,
                    'message': f'Payment status: {transaction.status}'
                })
                
            except MpesaTransaction.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Transaction not found'
                })
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid request data'
            })
        except Exception as e:
            logger.error(f"Check payment status error: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': 'An error occurred'
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Invalid request method'
    })

# Quick test endpoint
@csrf_exempt
def test_mpesa_connection(request):
    """Test M-Pesa connection and credentials"""
    if request.method == 'GET':
        mpesa = MpesaGateway()
        token = mpesa.get_access_token()
        
        if token:
            return JsonResponse({
                'success': True,
                'message': 'M-Pesa connection successful',
                'shortcode': mpesa.shortcode,
                'token_obtained': True,
                'callback_url': mpesa.callback_url
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'M-Pesa connection failed',
                'shortcode': mpesa.shortcode,
                'callback_url': mpesa.callback_url
            })

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