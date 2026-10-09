from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from .models import Review, Feedback

class ReviewTests(TestCase):
    def submit(self, kind='review', rating='5', text='A lovely report.', **extra):
        return self.client.post('/reviews/', {'submission_type': kind, f'{kind}-rating': rating, f'{kind}-text': text, **extra})

    def test_review_pending_even_when_client_requests_approval(self):
        response = self.submit(text='Pending secret review', approved='on')
        self.assertRedirects(response, reverse('reviews'))
        review = Review.objects.get()
        self.assertFalse(review.approved)
        self.assertEqual(review.rating, 5)
        self.assertNotContains(self.client.get('/reviews/'), review.text)

    def test_feedback_never_in_public_list(self):
        self.submit(kind='feedback', text='Private feedback secret', approved='on')
        self.assertTrue(Feedback.objects.exists())
        self.assertFalse(Review.objects.exists())
        self.assertNotContains(self.client.get('/reviews/'), 'Private feedback secret')
        self.assertNotContains(self.client.get('/reviews/?submission_type=feedback'), 'Private feedback secret')

    def test_rating_and_text_validation(self):
        for rating, text in [('0', 'Test'), ('6', 'Test'), ('invalid', 'Test'), ('5', ''), ('5', 'x' * 2001)]:
            self.assertEqual(self.submit(rating=rating, text=text).status_code, 200)
        for text in ['', 'x' * 2001]:
            self.assertEqual(self.submit(kind='feedback', text=text).status_code, 200)
        self.assertFalse(Review.objects.exists())
        self.assertFalse(Feedback.objects.exists())

    def test_only_approved_visible_and_html_escaped(self):
        Review.objects.create(rating=4, text='Hidden pending', approved=False)
        Review.objects.create(rating=5, text='<script>alert("test")</script>', approved=True)
        response = self.client.get('/reviews/')
        self.assertNotContains(response, 'Hidden pending')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(')
        self.assertContains(response, '5 out of 5 stars')

    def test_admin_approval_and_revocation(self):
        self.submit(text='Review awaiting moderation')
        review = Review.objects.get()
        user = get_user_model().objects.create_superuser('review-admin', 'admin@example.com', 'test-password')
        self.client.force_login(user)
        url = reverse('admin:studio_review_change', args=[review.pk])
        self.assertEqual(self.client.post(url, {'approved': 'on', '_save': 'Save'}).status_code, 302)
        self.assertContains(self.client.get('/reviews/'), review.text)
        self.client.post(url, {'_save': 'Save'})
        self.assertNotContains(self.client.get('/reviews/'), review.text)
        feedback = Feedback.objects.create(rating=3, text='Private admin note')
        self.assertContains(self.client.get(reverse('admin:studio_feedback_change', args=[feedback.pk])), feedback.text)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('admin:studio_feedback_changelist')).status_code, 302)

    def test_csrf_and_unknown_submission_type(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/reviews/', {'submission_type': 'review'}).status_code, 403)
        self.assertEqual(self.client.post('/reviews/', {'submission_type': 'something-else'}).status_code, 400)

    def test_feedback_without_rating_and_collapsible_form(self):
        response = self.client.get('/reviews/')
        self.assertContains(response, 'There are no reviews yet.')
        self.assertNotContains(response, 'name="feedback-rating"')
        self.assertContains(response, 'Or submit a feedback')
        response = self.client.post('/reviews/', {'submission_type': 'feedback', 'feedback-text': 'Private text without stars'})
        self.assertRedirects(response, reverse('reviews'))
        self.assertIsNone(Feedback.objects.get().rating)
        self.assertNotContains(self.client.get('/reviews/'), 'Private text without stars')

    def test_three_star_selection_is_saved_as_three(self):
        self.submit(rating='3')
        self.assertEqual(Review.objects.get().rating, 3)

    def test_invalid_feedback_keeps_panel_open(self):
        response = self.submit(kind='feedback', text='')
        self.assertContains(response, 'class="feedback-panel" open')
