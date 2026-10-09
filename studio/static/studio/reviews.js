const picker = document.querySelector('.star-picker');
if (picker) {
  const choices = [...picker.querySelectorAll('.star-choice')];
  const status = document.getElementById('rating-status');
  const paint = (value) => choices.forEach(choice => choice.classList.toggle('filled', Number(choice.dataset.rating) <= value));
  const selected = () => Number(picker.querySelector('input:checked')?.value || 0);
  const update = () => {
    const value = selected();
    paint(value);
    status.textContent = value ? `${value} out of 5 stars` : 'Choose your stars';
  };
  picker.addEventListener('change', update);
  choices.forEach(choice => choice.addEventListener('pointerenter', () => paint(Number(choice.dataset.rating))));
  picker.addEventListener('pointerleave', () => paint(selected()));
  update();
}
const feedback = document.getElementById('feedback-panel');
document.getElementById('cancel-feedback')?.addEventListener('click', () => {
  feedback.open = false;
  feedback.querySelector('summary').focus();
});
