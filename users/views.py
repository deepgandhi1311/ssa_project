import secrets, requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.decorators import method_decorator
from two_factor.views.core import LoginView as TFLoginView
from .forms import UserRegistrationForm, EmailAuthenticationForm

RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"

def _hp_name(request):
    if "hp_name" not in request.session:
        request.session["hp_name"] = f"hp_{secrets.token_hex(8)}"
    return request.session["hp_name"]

class SecureTwoFactorLoginView(TFLoginView):
    template_name = "users/login.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["hp_name"] = _hp_name(self.request)
        ctx["RECAPTCHA_SITE_KEY"] = getattr(settings, "RECAPTCHA_SITE_KEY", "")
        return ctx

    def get(self, request, *args, **kwargs):
        # If you previously added an unconditional reset() here, REMOVE it.
        # Resetting here would kick you back to the auth step after any redirect.
        _hp_name(request)  # just ensure a honeypot name exists
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        # Determine the current wizard step
        try:
            current_step = self.steps.current  # WizardView API
        except Exception:
            current_step = None

        # Run bot checks ONLY on the username/password step
        if current_step == 'auth':
            hp_name = request.session.get("hp_name", "hp_fallback")
            if request.POST.get(hp_name):
                messages.error(request, "Bot detected.")
                return redirect('users:login')

            try:
                elapsed = float(request.POST.get("elapsed", 0))
                if elapsed < 1.5:
                    messages.error(request, "Please wait a moment before submitting.")
                    return redirect('users:login')
            except (TypeError, ValueError):
                pass

            token = request.POST.get("recaptcha-token")
            if getattr(settings, "RECAPTCHA_SECRET_KEY", None):
                try:
                    r = requests.post(
                        RECAPTCHA_VERIFY_URL,
                        data={
                            "secret": settings.RECAPTCHA_SECRET_KEY,
                            "response": token,
                            "remoteip": request.META.get("REMOTE_ADDR"),
                        },
                        timeout=3.0,
                    )
                    rc = r.json()
                except requests.RequestException:
                    rc = {"success": False}

                ok = rc.get("success", False)
                score = rc.get("score")
                if not ok or (score is not None and score < 0.5):
                    messages.error(request, "reCAPTCHA validation failed. Please try again.")
                    return redirect('users:login')

        # For the OTP step, do NOT run any of the above checks.
        # Let two-factor handle the token validation.
        return super().post(request, *args, **kwargs)

def register(request):
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your account has been created! You can now log in.")
            return redirect('users:login')
    else:
        form = UserRegistrationForm()
    return render(request, 'users/register.html', {'form': form})

@login_required(login_url='users:login')
def user(request):
    return render(request, "chipin/home.html")

def logout_view(request):
    logout(request)
    messages.success(request, "Successfully logged out.")
    return redirect('users:login')