/// Password rules for new accounts (Day 23): shown as a live checklist with a strength bar,
/// and "Create account" only unlocks when every rule is met.
class PasswordRule {
  const PasswordRule(this.label, this.test);
  final String label;
  final bool Function(String password, String name, String email) test;
}

final passwordRules = <PasswordRule>[
  PasswordRule('At least 8 characters', (p, _, _) => p.length >= 8),
  PasswordRule(
    'An uppercase and a lowercase letter',
    (p, _, _) => p.contains(RegExp('[A-Z]')) && p.contains(RegExp('[a-z]')),
  ),
  PasswordRule('A number', (p, _, _) => p.contains(RegExp(r'\d'))),
  PasswordRule('A symbol (e.g. ! @ # \$ %)', (p, _, _) => p.contains(RegExp(r'[^A-Za-z0-9\s]'))),
  PasswordRule("Doesn't contain your name or email", (p, name, email) => !containsPersonal(p, name, email)),
];

/// True if the password contains part of the user's name (3+ letters) or of their email.
bool containsPersonal(String password, String name, String email) {
  final p = password.toLowerCase();
  final parts = [
    ...name.toLowerCase().split(RegExp(r'[^a-zÀ-￿]+')),
    email.toLowerCase().split('@').first,
  ].where((w) => w.length >= 3);
  return parts.any(p.contains);
}

bool passwordOk(String password, String name, String email) =>
    passwordRules.every((r) => r.test(password, name, email));

/// 0 (empty) ... 4 (strong), for the strength bar.
int passwordStrength(String password, String name, String email) {
  if (password.isEmpty) return 0;
  final met = passwordRules.where((r) => r.test(password, name, email)).length;
  var score = (met * 4 / passwordRules.length).floor();
  if (met == passwordRules.length && password.length >= 12) score = 4;
  if (met == passwordRules.length && password.length < 12) score = 3;
  return score.clamp(1, 4);
}

const strengthLabels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
