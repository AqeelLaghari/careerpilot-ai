import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../services/profile_store.dart';
import '../../theme.dart';
import 'profile_form.dart';

/// "My profile" (from the account menu): edit everything given at sign-up, plus account
/// details (email, sign-in method, change password).
class MyProfileScreen extends StatefulWidget {
  const MyProfileScreen({super.key});

  @override
  State<MyProfileScreen> createState() => _MyProfileScreenState();
}

class _MyProfileScreenState extends State<MyProfileScreen> {
  late final ProfileFormData _data = ProfileFormData(profileStore.profile);
  bool _saving = false;

  @override
  void dispose() {
    _data.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final problems = _data.checkAbout();
    _data.showErrors(problems);
    if (problems.isNotEmpty) return;
    setState(() => _saving = true);
    try {
      await profileStore.save({..._data.about(), ..._data.career(), 'completed': true});
      _data.showErrors({});
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Profile saved')));
    } on ApiException catch (e) {
      _data.showErrors(e.fieldErrors);
      if (mounted && e.fieldErrors.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not save: $e')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _changePassword(String email) async {
    await FirebaseAuth.instance.sendPasswordResetEmail(email: email);
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('We emailed a link to $email to choose a new password.')));
    }
  }

  Widget _card(String title, IconData icon, Widget child) => Card(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(icon, color: AppColors.brand),
              const SizedBox(width: 10),
              Text(title, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 20),
          child,
        ],
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final user = FirebaseAuth.instance.currentUser;
    final usesPassword = user?.providerData.any((p) => p.providerId == 'password') ?? false;
    final usesGoogle = user?.providerData.any((p) => p.providerId == 'google.com') ?? false;
    return Scaffold(
      appBar: AppBar(
        title: const Text('My profile'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: FilledButton.tonalIcon(
              onPressed: _saving ? null : _save,
              icon: const Icon(Icons.save_outlined),
              label: const Text('Save'),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 720),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _card('About you', Icons.person_outline, AboutYouSection(data: _data)),
                  const SizedBox(height: 8),
                  _card('Career goals', Icons.flag_outlined, CareerSection(data: _data)),
                  const SizedBox(height: 8),
                  _card(
                    'Account',
                    Icons.lock_outline,
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const Icon(Icons.mail_outline),
                          title: Text(user?.email ?? ''),
                          subtitle: Text(
                            [
                              if (usesGoogle) 'Signs in with Google',
                              if (usesPassword) 'Signs in with email and password',
                            ].join(' · '),
                          ),
                          trailing: (user?.emailVerified ?? false)
                              ? Chip(
                                  avatar: Icon(Icons.verified, size: 16, color: AppColors.good),
                                  label: Text('Verified'),
                                )
                              : null,
                        ),
                        if (usesPassword && user?.email != null)
                          Align(
                            alignment: Alignment.centerLeft,
                            child: OutlinedButton.icon(
                              onPressed: () => _changePassword(user!.email!),
                              icon: const Icon(Icons.key_outlined),
                              label: const Text('Change password'),
                            ),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  Center(
                    child: FilledButton.icon(
                      onPressed: _saving ? null : _save,
                      icon: const Icon(Icons.save_outlined),
                      label: const Padding(padding: EdgeInsets.all(10), child: Text('Save changes')),
                    ),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
