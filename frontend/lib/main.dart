import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'config.dart';
import 'firebase_options.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/verify_email_screen.dart';
import 'screens/home_shell.dart';
import 'screens/profile/profile_setup_screen.dart';
import 'services/api_client.dart';
import 'services/profile_store.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: currentFirebaseOptions);
  runApp(const CareerPilotApp());
}

class CareerPilotApp extends StatelessWidget {
  const CareerPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CareerPilot AI',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: const AuthGate(),
    );
  }
}

/// Decides what to show (Day 23):
///   logged out                      -> log in / create account
///   new email account, not verified -> "check your inbox"
///   profile not filled in yet       -> profile setup (steps 2 and 3)
///   otherwise                       -> the app
class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  late final StreamSubscription<User?> _sub;
  bool _started = false;
  String? _uid;
  Future<void>? _profile;

  @override
  void initState() {
    super.initState();
    _sub = FirebaseAuth.instance.userChanges().listen((user) {
      if (!mounted) return;
      setState(() {
        _started = true;
        if (user?.uid != _uid) {
          _uid = user?.uid;
          _profile = null; // another user: load their profile
          if (user == null) profileStore.clear();
        }
      });
    });
  }

  @override
  void dispose() {
    _sub.cancel();
    super.dispose();
  }

  /// Email/password accounts made since [verifyEmailFrom] must verify their email first.
  static bool needsVerification(User user) {
    final providers = user.providerData.map((p) => p.providerId).toSet();
    if (user.emailVerified || !providers.contains('password') || providers.contains('google.com')) return false;
    final created = user.metadata.creationTime;
    return created != null && !created.isBefore(verifyEmailFrom);
  }

  void _reload() => setState(() => _profile = null);

  @override
  Widget build(BuildContext context) {
    final user = FirebaseAuth.instance.currentUser;
    if (!_started) return const _Loading();
    if (user == null) return const LoginScreen();
    if (needsVerification(user)) return VerifyEmailScreen(onVerified: _reload);
    _profile ??= profileStore.load();
    return FutureBuilder<void>(
      future: _profile,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) return const _Loading();
        final error = snap.error;
        if (error is ApiException && error.statusCode == 403) {
          return VerifyEmailScreen(onVerified: _reload); // the server says: not verified yet
        }
        if (error != null) return _Offline(error: '$error', onRetry: _reload);
        if (!profileStore.completed) return ProfileSetupScreen(onDone: () => setState(() {}));
        return const HomeShell();
      },
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading();

  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: CircularProgressIndicator()));
}

/// The backend couldn't be reached (e.g. not started yet).
class _Offline extends StatelessWidget {
  const _Offline({required this.error, required this.onRetry});
  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            const Text('Could not reach the CareerPilot server.', style: TextStyle(fontSize: 18)),
            const SizedBox(height: 6),
            Text(
              error.replaceFirst('Exception: ', ''),
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.grey),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Try again')),
            TextButton(onPressed: () => FirebaseAuth.instance.signOut(), child: const Text('Log out')),
          ],
        ),
      ),
    ),
  );
}
