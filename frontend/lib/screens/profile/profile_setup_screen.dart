import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../services/profile_store.dart';
import '../../theme.dart';
import 'profile_form.dart';

/// After creating an account (step 1): step 2 "About you" and step 3 "Career goals" (optional).
/// Pre-filled from the Google account and, if one was uploaded, the CV.
class ProfileSetupScreen extends StatefulWidget {
  const ProfileSetupScreen({super.key, required this.onDone});
  final VoidCallback onDone;

  @override
  State<ProfileSetupScreen> createState() => _ProfileSetupScreenState();
}

class _ProfileSetupScreenState extends State<ProfileSetupScreen> {
  late final ProfileFormData _data;
  int _step = 0; // 0 = about you, 1 = career goals
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final user = FirebaseAuth.instance.currentUser;
    _data = ProfileFormData({
      ...profileStore.suggested, // from the CV
      if ((user?.displayName ?? '').isNotEmpty) 'full_name': user!.displayName,
      ...profileStore.profile, // anything already saved wins
    });
  }

  @override
  void dispose() {
    _data.dispose();
    super.dispose();
  }

  Future<void> _next() async {
    final problems = _data.checkAbout();
    _data.showErrors(problems);
    if (problems.isNotEmpty) return;
    if (await _save(_data.about())) setState(() => _step = 1);
  }

  Future<void> _finish({bool skipCareer = false}) async {
    final fields = {if (!skipCareer) ..._data.career(), 'completed': true};
    if (await _save(fields)) widget.onDone();
  }

  Future<bool> _save(Map<String, dynamic> fields) async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await profileStore.save(fields);
      _data.showErrors({});
      return true;
    } on ApiException catch (e) {
      _data.showErrors(e.fieldErrors);
      // a problem in "About you" while on step 3: go back to it
      if (e.fieldErrors.keys.any(ProfileFormData.aboutFields.contains)) setState(() => _step = 0);
      setState(() => _error = e.fieldErrors.isEmpty ? e.message : null);
      return false;
    } catch (e) {
      setState(() => _error = 'Could not save: $e');
      return false;
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final titles = ['Tell us about yourself', 'Your career goals'];
    final subtitles = [
      'This personalises your dashboard, career matches and interviews.',
      'Optional, and you can change it any time in "My profile".',
    ];
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.rocket_launch, color: AppColors.brand),
                      const SizedBox(width: 8),
                      Text('CareerPilot AI', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                      const Spacer(),
                      TextButton(onPressed: () => FirebaseAuth.instance.signOut(), child: const Text('Log out')),
                    ],
                  ),
                  const SizedBox(height: 20),
                  _Progress(step: _step + 2, total: 3),
                  const SizedBox(height: 20),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(28),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            titles[_step],
                            style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
                          ),
                          const SizedBox(height: 4),
                          Text(subtitles[_step], style: TextStyle(color: Colors.grey.shade600)),
                          const SizedBox(height: 24),
                          AnimatedSwitcher(
                            duration: const Duration(milliseconds: 250),
                            child: _step == 0
                                ? AboutYouSection(key: const ValueKey('about'), data: _data)
                                : CareerSection(key: const ValueKey('career'), data: _data),
                          ),
                          if (_error != null) ...[
                            const SizedBox(height: 14),
                            Text(_error!, style: const TextStyle(color: AppColors.bad)),
                          ],
                          const SizedBox(height: 24),
                          Row(
                            children: [
                              if (_step == 1)
                                TextButton.icon(
                                  onPressed: _saving ? null : () => setState(() => _step = 0),
                                  icon: const Icon(Icons.arrow_back),
                                  label: const Text('Back'),
                                ),
                              const Spacer(),
                              if (_step == 1)
                                TextButton(
                                  onPressed: _saving ? null : () => _finish(skipCareer: true),
                                  child: const Text('Skip for now'),
                                ),
                              const SizedBox(width: 8),
                              FilledButton(
                                onPressed: _saving ? null : (_step == 0 ? _next : _finish),
                                style: FilledButton.styleFrom(
                                  padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 16),
                                ),
                                child: _saving
                                    ? const SizedBox(
                                        width: 18,
                                        height: 18,
                                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                      )
                                    : Text(_step == 0 ? 'Continue' : 'Finish'),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// "Step 2 of 3" with a bar (step 1 was creating the account).
class _Progress extends StatelessWidget {
  const _Progress({required this.step, required this.total});
  final int step, total;

  @override
  Widget build(BuildContext context) {
    const labels = ['Account', 'About you', 'Career goals'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Step $step of $total',
          style: TextStyle(color: Colors.grey.shade600, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            for (var i = 1; i <= total; i++) ...[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 300),
                      height: 6,
                      decoration: BoxDecoration(
                        color: i <= step ? AppColors.brand : Colors.grey.shade300,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      labels[i - 1],
                      style: TextStyle(
                        fontSize: 12,
                        color: i <= step ? AppColors.brand : Colors.grey,
                        fontWeight: i == step ? FontWeight.w700 : FontWeight.normal,
                      ),
                    ),
                  ],
                ),
              ),
              if (i < total) const SizedBox(width: 8),
            ],
          ],
        ),
      ],
    );
  }
}
