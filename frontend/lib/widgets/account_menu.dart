import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../screens/profile/my_profile_screen.dart';
import '../services/profile_store.dart';
import '../theme.dart';
import 'brand.dart';
import 'user_avatar.dart';

/// The user's photo + name in the top bar; click for the account menu (Day 23).
/// (Settings such as theme and interview language join this menu on Day 24.)
class AccountMenu extends StatelessWidget {
  const AccountMenu({super.key});

  Future<void> _logOut(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.logout),
        title: const Text('Log out?'),
        content: const Text('Your CV, roadmap and interviews stay saved in your account.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.bad),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Log out'),
          ),
        ],
      ),
    );
    if (ok == true) {
      profileStore.clear();
      await FirebaseAuth.instance.signOut();
    }
  }

  void _about(BuildContext context) => showAboutDialog(
    context: context,
    applicationName: 'CareerPilot AI',
    applicationVersion: 'Version 1.0',
    applicationIcon: const BrandLogo.icon(size: 48),
    children: const [
      Text(
        'Your 24/7 AI career counselor: ATS resume check, career matches and roadmap, remote jobs, '
        'and live AI mock interviews.',
      ),
    ],
  );

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 700;
    return ListenableBuilder(
      listenable: profileStore,
      builder: (context, _) => PopupMenuButton<String>(
        tooltip: 'Account',
        offset: const Offset(0, 52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        onSelected: (v) => switch (v) {
          'profile' => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const MyProfileScreen())),
          'about' => _about(context),
          'logout' => _logOut(context),
          _ => null,
        },
        itemBuilder: (_) => [
          PopupMenuItem<String>(
            enabled: false,
            child: SizedBox(
              width: 260,
              child: Row(
                children: [
                  const UserAvatar(radius: 22),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          profileStore.name,
                          style: const TextStyle(fontWeight: FontWeight.w700, color: Colors.black87),
                          overflow: TextOverflow.ellipsis,
                        ),
                        Text(
                          FirebaseAuth.instance.currentUser?.email ?? '',
                          style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                          overflow: TextOverflow.ellipsis,
                        ),
                        if (profileStore.subtitle.isNotEmpty)
                          Text(
                            profileStore.subtitle,
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                            overflow: TextOverflow.ellipsis,
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const PopupMenuDivider(),
          const PopupMenuItem(
            value: 'profile',
            child: ListTile(leading: Icon(Icons.person_outline), title: Text('My profile'), dense: true),
          ),
          if ((profileStore.profile['target_role'] as String?)?.isNotEmpty ?? false)
            PopupMenuItem(
              value: 'profile',
              child: ListTile(
                leading: const Icon(Icons.flag_outlined),
                title: Text('Target: ${profileStore.profile['target_role']}', overflow: TextOverflow.ellipsis),
                dense: true,
              ),
            ),
          const PopupMenuItem(
            value: 'about',
            child: ListTile(leading: Icon(Icons.help_outline), title: Text('Help & about'), dense: true),
          ),
          const PopupMenuDivider(),
          const PopupMenuItem(
            value: 'logout',
            child: ListTile(
              leading: Icon(Icons.logout, color: AppColors.bad),
              title: Text('Log out', style: TextStyle(color: AppColors.bad)),
              dense: true,
            ),
          ),
        ],
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.all(2),
                decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                child: const UserAvatar(radius: 16),
              ),
              if (wide) ...[
                const SizedBox(width: 8),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 160),
                  child: Text(
                    profileStore.firstName,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
              const Icon(Icons.arrow_drop_down, color: Colors.white),
            ],
          ),
        ),
      ),
    );
  }
}
