from __future__ import unicode_literals

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User as UserAuth
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import resolve_url
from django.utils.decorators import method_decorator
from django.utils.http import is_safe_url
from django.views.generic import TemplateView, FormView
from planbox_data.models import Project, Profile
from planbox_data.serializers import ProjectSerializer, UserSerializer
from planbox_ui.decorators import ssl_required
from planbox_ui.forms import UserCreationForm


class AppMixin (object):
    def get_home_url(self, obj):
        if obj is None and self.request.user.is_authenticated():
            obj = self.request.user

        if isinstance(obj, UserAuth):
            owner_name = obj.username
        elif isinstance(obj, Profile):
            owner_name = obj.slug
        return resolve_url('app-new-project', owner_name=owner_name)


class LoginRequired (object):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(LoginRequired, self).dispatch(request, *args, **kwargs)


class SSLRequired (object):
    @method_decorator(ssl_required)
    def dispatch(self, request, *args, **kwargs):
        return super(SSLRequired, self).dispatch(request, *args, **kwargs)


# App
class IndexView (TemplateView):
    template_name = 'index.html'


class SignupView (AppMixin, SSLRequired, FormView):
    template_name = 'signup.html'
    form_class = UserCreationForm

    def get_initial(self):
        initial = super(SignupView, self).get_initial()
        if 'email' in self.request.GET:
            initial['email'] = self.request.GET['email']
        return initial

    def get_success_url(self):
        return self.get_home_url(self.auth)

    def form_valid(self, form):
        form.save()
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        self.auth = authenticate(username=username, password=password)
        login(self.request, self.auth)
        return super(SignupView, self).form_valid(form)


class PasswordResetView (TemplateView):
    template_name = 'password-reset.html'


class SigninView (AppMixin, SSLRequired, FormView):
    template_name = 'signin.html'
    form_class = AuthenticationForm

    def get_context_data(self, **kwargs):
        if 'next' in self.request.GET:
            kwargs['next_url'] = self.request.GET['next']
        return super(SigninView, self).get_context_data(**kwargs)

    def get_success_url(self):
        # Ensure the user-originating redirection url is safe.
        redirect_to = self.request.REQUEST.get('next', self.get_home_url(self.auth))
        if not is_safe_url(url=redirect_to, host=self.request.get_host()):
            redirect_to = resolve_url(settings.LOGIN_REDIRECT_URL)
        return redirect_to

    def form_valid(self, form):
        # Okay, security check complete. Log the user in.
        self.auth = form.get_user()
        login(self.request, self.auth)
        return super(SigninView, self).form_valid(form)


class ProjectView (SSLRequired, TemplateView):
    template_name = 'project.html'

    def get_context_data(self, **kwargs):
        context = super(ProjectView, self).get_context_data(**kwargs)

        if (self.request.user.is_authenticated()):
            try:
                user_profile = self.request.user.profile
            except Profile.DoesNotExist:
                user_profile = None
        else:
            user_profile = None

        user_serializer = UserSerializer(user_profile)
        project_serializer = ProjectSerializer(self.project)

        context['user_data'] = None if user_profile is None else user_serializer.data
        context['project_data'] = project_serializer.data
        context['is_owner'] = self.project.owned_by(user_profile)

        return context

    def get(self, request, owner_name, slug):
        self.project = get_object_or_404(Project, owner__slug=owner_name, slug=slug)

        if not (self.project.public or self.project.owned_by(self.request.user)):
            raise Http404

        return super(ProjectView, self).get(request, pk=self.project.pk)


class NewProjectView (LoginRequired, SSLRequired, TemplateView):
    template_name = 'project.html'

    def get_context_data(self, **kwargs):
        context = super(NewProjectView, self).get_context_data(**kwargs)

        user_serializer = UserSerializer(self.request.user.profile)
        context['project_data'] = {}
        context['user_data'] = user_serializer.data
        context['is_owner'] = True

        return context

    def get(self, request, owner_name):
        # Check whether this page is for the auth'd user
        if owner_name != request.user.username:
            return redirect('app-new-project', owner_name=self.request.user.username)

        owner_auth = get_object_or_404(UserAuth, username=owner_name)

        if 'force_new' not in request.GET:
            # Check whether the user has an existing project and redirect there.
            try:
                project = owner_auth.profile.projects.all()[0]
            except IndexError:
                pass
            else:
                return redirect('app-project', owner_name=owner_name, slug=project.slug)

        return super(NewProjectView, self).get(request, owner_name)


# SEO
class SiteMapView (AppMixin, TemplateView):
    template_name = 'sitemap.xml'

    def get_project_queryset(self):
        return Project.objects.filter(public=True).select_related('owner')

    def get_context_data(self, **kwargs):
        context = super(SiteMapView, self).get_context_data(**kwargs)
        context['projects'] = self.get_project_queryset()
        return context


# App views
index_view = IndexView.as_view()
project_view = ProjectView.as_view()
new_project_view = NewProjectView.as_view()
signup_view = SignupView.as_view()
signin_view = SigninView.as_view()
password_reset_view = PasswordResetView.as_view()
robots_view = TemplateView.as_view(template_name='robots.txt', content_type='text/plain')
sitemap_view = SiteMapView.as_view(content_type='text/xml')
