import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../services/password_rules.dart';
import '../../theme.dart';
import '../../widgets/brand.dart';

/// Log in / create an account (Day 23): Google sign-in, or email + password with password
/// rules, show/hide, confirm, and "Forgot password?". After sign-up Firebase emails a
/// verification link (see verify_email_screen.dart).
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  bool _signUp = false;
  bool _busy = false;
  bool _showPassword = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    for (final c in [_name, _email, _password, _confirm]) {
      c.addListener(() => setState(() {})); // live checklist + button state
    }
  }

  @override
  void dispose() {
    for (final c in [_name, _email, _password, _confirm]) {
      c.dispose();
    }
    super.dispose();
  }

  bool get _emailOk => RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(_email.text.trim());

  bool get _canSubmit {
    if (_busy || !_emailOk || _password.text.isEmpty) return false;
    if (!_signUp) return true;
    return _name.text.trim().length >= 2 &&
        passwordOk(_password.text, _name.text, _email.text) &&
        _password.text == _confirm.text;
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      // No navigation: the app listens for login and switches screens by itself.
    } on FirebaseAuthException catch (e) {
      if (mounted && e.code != 'popup-closed-by-user' && e.code != 'cancelled-popup-request') {
        setState(() => _error = _friendly(e));
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submit() => _run(() async {
    final auth = FirebaseAuth.instance;
    final email = _email.text.trim();
    if (_signUp) {
      final cred = await auth.createUserWithEmailAndPassword(email: email, password: _password.text);
      await cred.user?.updateDisplayName(_name.text.trim());
      await cred.user?.sendEmailVerification();
    } else {
      await auth.signInWithEmailAndPassword(email: email, password: _password.text);
    }
  });

  Future<void> _google() => _run(() async {
    final provider = GoogleAuthProvider()..setCustomParameters({'prompt': 'select_account'});
    if (kIsWeb) {
      await FirebaseAuth.instance.signInWithPopup(provider);
    } else {
      await FirebaseAuth.instance.signInWithProvider(provider);
    }
  });

  Future<void> _forgotPassword() async {
    final email = TextEditingController(text: _email.text.trim());
    final send = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reset your password'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text("We'll email you a link to choose a new password."),
            const SizedBox(height: 16),
            TextField(
              controller: email,
              autofocus: true,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'Email', border: OutlineInputBorder()),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Send link')),
        ],
      ),
    );
    if (send != true || email.text.trim().isEmpty) return;
    try {
      await FirebaseAuth.instance.sendPasswordResetEmail(email: email.text.trim());
    } on FirebaseAuthException catch (e) {
      if (e.code == 'invalid-email') {
        if (mounted) setState(() => _error = 'That email address is not valid.');
        return;
      }
      // other errors (e.g. no such user) are not shown, so nobody can test which emails have accounts
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('If an account exists for ${email.text.trim()}, a reset link is on its way.')),
    );
  }

  static String _friendly(FirebaseAuthException e) => switch (e.code) {
    'invalid-credential' || 'wrong-password' || 'user-not-found' => 'Wrong email or password.',
    'email-already-in-use' => 'An account with this email already exists. Log in instead.',
    'invalid-email' => 'That email address is not valid.',
    'weak-password' => 'Please choose a stronger password.',
    'too-many-requests' => 'Too many attempts. Please wait a minute and try again.',
    'network-request-failed' => 'No internet connection.',
    'account-exists-with-different-credential' =>
      'This email already has a password account. Log in with your email and password.',
    'popup-blocked' => 'The browser blocked the Google window. Allow pop-ups for this site and try again.',
    'user-disabled' => 'This account has been disabled.',
    _ => e.message ?? 'Something went wrong (${e.code}).',
  };

  // ------------------------------------------------------------------- UI --
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: LayoutBuilder(
        builder: (context, box) {
          final wide = box.maxWidth >= 900;
          final form = Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
              child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 420), child: _form(context, wide)),
            ),
          );
          if (!wide) return form;
          return Row(
            children: [
              const Expanded(flex: 5, child: _BrandPanel()),
              Expanded(flex: 6, child: form),
            ],
          );
        },
      ),
    );
  }

  Widget _form(BuildContext context, bool wide) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (!wide) ...[const Center(child: BrandLogo.horizontal(size: 46)), const SizedBox(height: 28)],
        Text(
          _signUp ? 'Create your account' : 'Welcome back',
          style: theme.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 4),
        Text(
          _signUp ? 'Start with your CV and get a career plan in minutes.' : 'Log in to continue your career plan.',
          style: theme.textTheme.bodyMedium?.copyWith(color: Colors.grey.shade600),
        ),
        const SizedBox(height: 24),
        OutlinedButton(
          onPressed: _busy ? null : _google,
          style: OutlinedButton.styleFrom(
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
          child: const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _GoogleMark(),
              SizedBox(width: 12),
              Text('Continue with Google', style: TextStyle(fontSize: 15)),
            ],
          ),
        ),
        const SizedBox(height: 20),
        Row(
          children: [
            const Expanded(child: Divider()),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text('or with email', style: TextStyle(color: Colors.grey.shade600)),
            ),
            const Expanded(child: Divider()),
          ],
        ),
        const SizedBox(height: 20),
        if (_signUp) ...[
          _field(_name, 'Full name', Icons.person_outline, autofill: AutofillHints.name),
          const SizedBox(height: 14),
        ],
        _field(
          _email,
          'Email',
          Icons.mail_outline,
          keyboard: TextInputType.emailAddress,
          autofill: AutofillHints.email,
          error: _email.text.isNotEmpty && !_emailOk ? 'Enter a valid email address' : null,
        ),
        const SizedBox(height: 14),
        _field(
          _password,
          'Password',
          Icons.lock_outline,
          obscure: !_showPassword,
          autofill: _signUp ? AutofillHints.newPassword : AutofillHints.password,
          suffix: IconButton(
            tooltip: _showPassword ? 'Hide password' : 'Show password',
            icon: Icon(_showPassword ? Icons.visibility_off : Icons.visibility),
            onPressed: () => setState(() => _showPassword = !_showPassword),
          ),
          onSubmit: _signUp ? null : _submit,
        ),
        if (!_signUp)
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(onPressed: _busy ? null : _forgotPassword, child: const Text('Forgot password?')),
          ),
        if (_signUp) ...[
          const SizedBox(height: 12),
          PasswordChecklist(password: _password.text, name: _name.text, email: _email.text),
          const SizedBox(height: 14),
          _field(
            _confirm,
            'Confirm password',
            Icons.lock_outline,
            obscure: !_showPassword,
            autofill: AutofillHints.newPassword,
            error: _confirm.text.isNotEmpty && _confirm.text != _password.text ? "Passwords don't match" : null,
            onSubmit: _submit,
          ),
        ],
        if (_error != null) ...[
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.bad.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(
              children: [
                Icon(Icons.error_outline, color: AppColors.bad, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(_error!, style: TextStyle(color: AppColors.bad)),
                ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 20),
        FilledButton(
          onPressed: _canSubmit ? _submit : null,
          style: FilledButton.styleFrom(
            padding: const EdgeInsets.symmetric(vertical: 16),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
          child: _busy
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : Text(_signUp ? 'Create account' : 'Log in', style: const TextStyle(fontSize: 16)),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_signUp ? 'Already have an account?' : 'New to CareerPilot?'),
            TextButton(
              onPressed: _busy
                  ? null
                  : () => setState(() {
                      _signUp = !_signUp;
                      _error = null;
                    }),
              child: Text(_signUp ? 'Log in' : 'Create an account'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _field(
    TextEditingController c,
    String label,
    IconData icon, {
    bool obscure = false,
    TextInputType? keyboard,
    String? autofill,
    String? error,
    Widget? suffix,
    VoidCallback? onSubmit,
  }) => TextField(
    controller: c,
    obscureText: obscure,
    keyboardType: keyboard,
    autofillHints: autofill == null ? null : [autofill],
    onSubmitted: onSubmit == null ? null : (_) => _canSubmit ? onSubmit() : null,
    decoration: InputDecoration(
      labelText: label,
      prefixIcon: Icon(icon),
      suffixIcon: suffix,
      errorText: error,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
    ),
  );
}

/// The live password checklist and strength bar shown while creating an account.
class PasswordChecklist extends StatelessWidget {
  const PasswordChecklist({super.key, required this.password, required this.name, required this.email});
  final String password, name, email;

  static final _colours = [Colors.grey, AppColors.bad, AppColors.warn, Color(0xFF65A30D), AppColors.good];

  @override
  Widget build(BuildContext context) {
    final strength = passwordStrength(password, name, email);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            for (var i = 1; i <= 4; i++)
              Expanded(
                child: Container(
                  height: 6,
                  margin: EdgeInsets.only(right: i < 4 ? 4 : 0),
                  decoration: BoxDecoration(
                    color: i <= strength ? _colours[strength] : Colors.grey.shade300,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
              ),
            const SizedBox(width: 10),
            SizedBox(
              width: 52,
              child: Text(
                strengthLabels[strength],
                style: TextStyle(color: _colours[strength], fontWeight: FontWeight.w600, fontSize: 12),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        for (final rule in passwordRules)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(
              children: [
                Icon(
                  rule.test(password, name, email) ? Icons.check_circle : Icons.radio_button_unchecked,
                  size: 16,
                  color: rule.test(password, name, email) ? AppColors.good : Colors.grey,
                ),
                const SizedBox(width: 8),
                Text(rule.label, style: const TextStyle(fontSize: 13)),
              ],
            ),
          ),
      ],
    );
  }
}

/// Left side on wide screens: the product in one glance.
class _BrandPanel extends StatelessWidget {
  const _BrandPanel();

  @override
  Widget build(BuildContext context) {
    const features = [
      (Icons.fact_check_outlined, 'ATS resume check', 'See how hiring systems read your CV, and fix it.'),
      (Icons.route_outlined, 'Career roadmap', 'Best-fit careers and a week-by-week learning plan.'),
      (Icons.work_outline, 'Remote jobs', 'Live jobs open to candidates in Pakistan, matched to you.'),
      (Icons.videocam_outlined, 'Live AI interview', 'A spoken video interview with a graded report.'),
    ];
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.navy, AppColors.navyMid, AppColors.navyLight],
        ),
      ),
      child: Stack(
        children: [
          // the "C" mark as a large, faint watermark (like the brand wallpaper)
          Positioned(
            right: -140,
            bottom: -120,
            child: Opacity(opacity: 0.07, child: BrandLogo.icon(size: 560, white: true)),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 56, vertical: 40),
            child: LayoutBuilder(builder: (context, box) => _content(features, box.maxWidth)),
          ),
        ],
      ),
    );
  }

  /// Logo first and big, then the headline, the tagline and what the app does.
  Widget _content(List<(IconData, String, String)> features, double width) {
    // the horizontal logo is ~4.3x wider than tall: let it take ~75% of the panel width
    final logoHeight = (width * 0.75 / 4.3).clamp(56.0, 120.0);
    // the logo file keeps a thin transparent margin (~2.8% of its width) on the left:
    // shift it so the "C" lines up exactly with the text below
    final logoWidth = logoHeight * 1000 / 232;
    final faint = Colors.white.withValues(alpha: 0.65);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Spacer(flex: 2),
        Transform.translate(
          offset: Offset(-logoWidth * 0.028, 0),
          child: BrandLogo.horizontal(size: logoHeight, white: true),
        ),
        const SizedBox(height: 32),
        Text(
          'Your 24/7 AI career counselor',
          style: GoogleFonts.inter(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600, height: 1.3),
        ),
        const SizedBox(height: 6),
        Text('From CV to interview-ready, in one place.', style: TextStyle(color: faint, fontSize: 13.5)),
        const SizedBox(height: 44),
        for (final (icon, title, text) in features)
          Padding(
            padding: const EdgeInsets.only(bottom: 20),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(icon, color: Colors.white, size: 17),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13.5),
                      ),
                      const SizedBox(height: 2),
                      Text(text, style: TextStyle(color: faint, fontSize: 12, height: 1.35)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        const Spacer(flex: 3),
        Text('© 2026 CareerPilot AI', style: TextStyle(color: Colors.white.withValues(alpha: 0.5), fontSize: 11)),
      ],
    );
  }
}

/// A simple Google "G" (drawn with text, so no image file is needed).
class _GoogleMark extends StatelessWidget {
  const _GoogleMark();

  @override
  Widget build(BuildContext context) => Container(
    width: 22,
    height: 22,
    alignment: Alignment.center,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      border: Border.all(color: Colors.grey.shade300),
    ),
    child: const Text(
      'G',
      style: TextStyle(color: Color(0xFF4285F4), fontWeight: FontWeight.w800, fontSize: 14),
    ),
  );
}
