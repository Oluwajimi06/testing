from django.shortcuts import render,redirect,get_object_or_404
from .models import FoodItem,Purchase,OrderItem,CheckoutDetails
from django.db import transaction
from uuid import uuid4
# import uuid 
#
from .forms import CheckoutForm

from django.contrib.auth.decorators import login_required

#
from accounts.forms import UserProfileForm



from accounts.models import  UserProfile
from django.urls import reverse
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
 


from decimal import Decimal
# # from paystackapi import Transaction
# from paystackapi.transaction import Transaction
# import paystack
import paystack


from datetime import datetime




from django.conf import settings
import time
import random
import logging
import requests
import json
from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect
from django.core.mail import send_mail
from django.views.decorators.http import require_POST


logger = logging.getLogger(__name__)

# Create your views here.
def Home(request):
    if 'usercart' in request.session:
        x=request.session['usercart']
        totalnumber = len(x)
    else:
        request.session['usercart']=[]
        x=request.session['usercart']
        totalnumber = len(x)


    mdata = FoodItem.objects.all()
    data={"ptitle":"Meals order & bookings - Home page","mdata":mdata,"ttl": totalnumber}
    return render(request,"sitepages/home.html",data)


def About(request):
    data={"ptitle":"Meals order & bookings - About Us"}
    return render(request,"sitepages/about.html",data)
def Service(request):
    data={"ptitle":"Meals order & bookings - Service"}
    return render(request,"sitepages/service.html",data)
def Booking(request):
    data={"ptitle":"Meals order & bookings - Booking"}
    return render(request,"sitepages/booking.html",data)
def Team(request):
    data={"ptitle":"Meals order & bookings - Our Team"}
    return render(request,"sitepages/team.html",data)
def Testimonial(request):
    data={"ptitle":"Meals order & bookings - Testimonial"}
    return render(request,"sitepages/testimonial.html",data)
def Contact(request):
    data={"ptitle":"Meals order & bookings - Contact Us"}
    return render(request,"sitepages/contact.html",data)
def Details(request,pid):
    x=request.session['usercart']
    print(len(x))
    mdata = FoodItem.objects.get(id=pid)
    data={"ptitle":"Meals order & bookings - Home page","mdata": mdata}
    return render(request,"sitepages/details.html",data)


def AddtoCart(request, pid):
    x = request.session['usercart']
    x.append(pid)
    request.session['usercart'] = x
    return redirect("/viewcart")

def RemovefromCart(request, pid):
    x = request.session['usercart']
    x.remove(pid)
    request.session['usercart'] = x
    return redirect("/viewcart")



def ViewCart(request):
    # Retrieve user cart from session or initialize an empty list
    x = request.session.get('usercart', [])
    y = []
    totalsum = 0
    delivery_fee = 1500

    # Loop through the unique items in the cart
    for i in set(x):
        m = FoodItem.objects.get(id=i)
        qty = x.count(i)
        unit_t = qty * int(m.price)
        totalsum += unit_t
        zee = dict(name=m.name, u_price=m.price, price=m.price, uqty=unit_t, qty=qty, pid=m.id, image=m.image.url)
        y.append(zee)

    # Store cart items in the session
    # Store cart items, totalsum, and delivery_fee in the session
    request.session['citems'] = y
    request.session['totalsum'] = totalsum
    request.session['delivery_fee'] = delivery_fee

   
    # Add delivery fee
      # Change this to your desired fixed delivery fee
    totalsum += delivery_fee  # Add the fixed delivery fee to the total

    # Check if the user is authenticated
    if request.user.is_authenticated:
        # Check if the user has an associated profile
        try:
            user_profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            user_profile = None

        # If the user has a profile, pre-fill the form with existing data
        form = UserProfileForm(instance=user_profile) if user_profile else UserProfileForm()

        return render(request, 'sitepages/viewcart.html', {'citems': y, 'tsum': totalsum, 'delivery_fee': delivery_fee, 'user_profile': user_profile, 'form': form})

    else:
        return redirect('/login')
        data = {"ptitle": "Meals order & bookings - Home page", "citems": y, "tsum": totalsum}
        return render(request, "sitepages/viewcart.html", data)




paystack_secret_key = settings.PAYSTACK_SECRET_KEY
paystack.api_key = paystack_secret_key

@login_required
def checkout(request):
    totalsum = request.session.get('totalsum', 0)
    delivery_fee = request.session.get('delivery_fee', 0)
    citems = request.session.get('citems', [])

    if request.method == 'POST':
        form = CheckoutForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                purchase, created = Purchase.objects.get_or_create(
                    user=request.user,
                    status='PENDING',
                    defaults={
                        'order_date': timezone.now(),
                        'delivery_address': form.cleaned_data['delivery_address'],
                        'phone_number': form.cleaned_data['phone_number'],
                    }
                )

                if not created:
                    purchase.delivery_address = form.cleaned_data['delivery_address']
                    purchase.phone_number = form.cleaned_data['phone_number']
                    purchase.save()

                checkout_details = CheckoutDetails(
                    user=request.user,
                    full_name=form.cleaned_data['full_name'],
                    email=form.cleaned_data['email'],
                    delivery_address=form.cleaned_data['delivery_address'],
                    phone_number=form.cleaned_data['phone_number'],
                    created_at=timezone.now(),
                )
                checkout_details.save()

                for item in citems:
                    OrderItem.objects.create(
                        purchase=purchase,
                        product_name=item['name'],
                        quantity=item['qty'],
                        unit_price=item['u_price'],
                        total_price=item['uqty']
                    )

                total_amount = totalsum + delivery_fee

                # Redirect to the initiate_payment page with the necessary details
                return redirect('sitepages:initiate_payment', order_id=purchase.id, total_amount=total_amount, email=form.cleaned_data['email'])
    else:
        form = CheckoutForm()

    return render(request, 'sitepages/checkout.html', {
        'form': form,
        'delivery_fee': delivery_fee,
        'totalsum': totalsum,
        'citems': citems,
    })



paystack_secret_key = settings.PAYSTACK_SECRET_KEY  # Replace with your actual Paystack secret key

@csrf_exempt
def initiate_payment(request, order_id, total_amount, email):
    try:
        paystack_api_url = "https://api.paystack.co/transaction/initialize"

        headers = {
            "Authorization": f"Bearer {paystack_secret_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "email": email,
            "amount": int(total_amount * 100),
            "currency": "NGN",
            "reference": str(uuid4()),
            # Other parameters as needed
        }

        print(payload)

        response = requests.post(paystack_api_url, json=payload, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors

        paystack_response = response.json()
        print(paystack_response)

        # Redirect the user to Paystack payment page
        return redirect(paystack_response['data']['authorization_url'])

    except requests.exceptions.RequestException as e:
        return HttpResponse(f"Failed to initiate payment: {e}", status=500)

    except requests.exceptions.HTTPError as e:
        # Print the response content for debugging purposes
        print(f"Paystack API response content: {e.response.content}")
        return HttpResponse(f"Failed to initiate payment: {e}", status=500)

    except Exception as e:
        return HttpResponse(f"An unexpected error occurred: {e}", status=500)







































