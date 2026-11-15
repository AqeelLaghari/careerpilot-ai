import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../../theme.dart';
import '../../widgets/brand.dart';

/// "Check your inbox" (Day 23): a new email/password account must click the link Firebase
/// emailed before using the app (the backend checks this too). Checks every few seconds, so
/// the app continues by itself once the link is clicked.
class VerifyEmailScreen extends StatefulWidget {
  const VerifyEmailScreen({super.key, required this.onVerified});
  final VoidCallback onVerified;

  @override
  State<VerifyEmailScreen> createState() => _VerifyEmailScreenState();
}

class _VerifyEmailScreenState extends State<VerifyEmailScreen> {
  Timer? _poll, _countdown;
  int _wait = 0; // seconds until "Resend" works again
  bool _checking = false;
  String? _message;

  @override
  void initState() {
    super.initState();
    _poll = Timer.periodic(const Duration(seconds: 5), (_) => _check(quiet: true));
    _startCooldown(); // a link was just sent at sign-up
  }

  @override
  void dispose() {
    _poll?.cancel();
    _countdown?.cancel();
    super.dispose();
  }

  void _startCooldown() {
    _wait = 60;
    _countdown?.cancel();
    _countdown = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return;
      setState(() => _wait--);
      if (_wait <= 0) t.cancel();
    });
  }

  Future<void> _check({bool quiet = false}) async {
    if (_checking) return;
    _checking = true;
    try {
      final user = FirebaseAuth.instance.currentUser;
      await user?.reload();
      final fresh = FirebaseAuth.instance.currentUser;
      if (fresh?.emailVerified ?? false) {
        await fresh!.getIdToken(true); // a new login token that says "verified", for the backend
        _poll?.cancel();
        widget.onVerified();
      } else if (!quiet && mounted) {
        setState(() => _message = "Not verified yet. Click the link in the email, then press this again.");
      }
    } catch (_) {
      if (!quiet && mounted) setState(() => _message = 'Could not check. Are you online?');
    } finally {
      _checking = false;
    }
  }

  Future<void> _resend() async {
    try {
      await FirebaseAuth.instance.currentUser?.sendEmailVerification();
      _startCooldown();
      if (mounted) setState(() => _message = 'A new link has been sent.');
    } on FirebaseAuthException catch (e) {
      if (mounted) {
        setState(
          () => _message = e.code == 'too-many-requests'
              ? 'Too many emails sent. Please wait a few minutes.'
              : (e.message ?? 'Could not send the email.'),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final email = FirebaseAuth.instance.currentUser?.email ?? 'your email';
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const BrandLogo.horizontal(size: 32),
                    const SizedBox(height: 28),
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(color: AppColors.brand.withValues(alpha: 0.08), shape: BoxShape.circle),
                      child: const Icon(Icons.mark_email_unread_outlined, size: 44, color: AppColors.brand),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      'Check your inbox',
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 10),
                    Text.rich(
                      TextSpan(
                        children: [
                          const TextSpan(text: 'We sent a verification link to\n'),
                          TextSpan(
                            text: email,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          const TextSpan(text: '.\nClick it to activate your account. Check the spam folder too.'),
                        ],
                      ),
                      textAlign: TextAlign.center,
                      style: const TextStyle(height: 1.5),
                    ),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: () => _check(),
                        icon: const Icon(Icons.check),
                        label: const Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: Text("I've verified my email"),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: _wait > 0 ? null : _resend,
                        icon: const Icon(Icons.refresh),
                        label: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: Text(_wait > 0 ? 'Resend link in $_wait s' : 'Resend link'),
                        ),
                      ),
                    ),
                    if (_message != null) ...[
                      const SizedBox(height: 14),
                      Text(
                        _message!,
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.grey.shade700),
                      ),
                    ],
                    const SizedBox(height: 18),
                    TextButton(
                      onPressed: () => FirebaseAuth.instance.signOut(),
                      child: const Text('Use a different email / log out'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
