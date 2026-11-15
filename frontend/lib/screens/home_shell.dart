import 'package:flutter/material.dart';

import '../services/profile_store.dart';
import '../theme.dart';
import '../widgets/account_menu.dart';
import '../widgets/brand.dart';
import '../widgets/user_avatar.dart';
import 'career/career_screen.dart';
import 'dashboard_screen.dart';
import 'interview/interview_screen.dart';
import 'jobs/jobs_screen.dart';
import 'profile/my_profile_screen.dart';
import 'resume/resume_screen.dart';
import 'settings/settings_screen.dart';

/// One section of the app.
class _Dest {
  const _Dest(this.id, this.label, this.icon, this.selectedIcon);
  final String id, label;
  final IconData icon, selectedIcon;
}

const _dests = [
  _Dest('dashboard', 'Dashboard', Icons.space_dashboard_outlined, Icons.space_dashboard),
  _Dest('resume', 'Resume', Icons.description_outlined, Icons.description),
  _Dest('career', 'Career', Icons.explore_outlined, Icons.explore),
  _Dest('jobs', 'Jobs', Icons.work_outline, Icons.work),
  _Dest('interview', 'Interview', Icons.videocam_outlined, Icons.videocam),
];

/// The main app frame after login (Day 24): top bar, and a left sidebar on wide screens
/// (photo, name, university, sections) or bottom tabs on phones.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  static const wideBreakpoint = 900.0;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _tab = 0;

  void _open(String id) {
    final i = _dests.indexWhere((d) => d.id == id);
    if (i >= 0) setState(() => _tab = i);
  }

  Widget _page() => switch (_dests[_tab].id) {
    'resume' => const ResumeScreen(),
    'career' => const CareerScreen(),
    'jobs' => const JobsScreen(),
    'interview' => const InterviewScreen(),
    _ => DashboardScreen(onOpen: _open),
  };

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= HomeShell.wideBreakpoint;
    final page = AnimatedSwitcher(
      duration: const Duration(milliseconds: 220),
      switchInCurve: Curves.easeOut,
      transitionBuilder: (child, a) => FadeTransition(opacity: a, child: child),
      child: KeyedSubtree(key: ValueKey(_tab), child: _page()),
    );
    return Scaffold(
      appBar: AppBar(
        title: const BrandLogo.horizontal(size: 30, white: true),
        actions: const [AccountMenu(), SizedBox(width: 8)],
      ),
      body: wide
          ? Row(
              children: [
                _Sidebar(selected: _tab, onSelect: (i) => setState(() => _tab = i)),
                Expanded(child: page),
              ],
            )
          : page,
      bottomNavigationBar: wide
          ? null
          : NavigationBar(
              selectedIndex: _tab,
              onDestinationSelected: (i) => setState(() => _tab = i),
              destinations: [
                for (final d in _dests)
                  NavigationDestination(icon: Icon(d.icon), selectedIcon: Icon(d.selectedIcon), label: d.label),
              ],
            ),
    );
  }
}

class _Sidebar extends StatelessWidget {
  const _Sidebar({required this.selected, required this.onSelect});
  final int selected;
  final ValueChanged<int> onSelect;

  void _push(BuildContext context, Widget screen) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 256,
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(right: BorderSide(color: AppColors.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // who is logged in
          ListenableBuilder(
            listenable: profileStore,
            builder: (context, _) => InkWell(
              onTap: () => _push(context, const MyProfileScreen()),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 24, 16, 20),
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
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14.5, color: AppColors.text),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            (profileStore.profile['university'] as String?) ??
                                profileStore.statuses[profileStore.profile['status']] ??
                                'View your profile',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 12, color: AppColors.textMuted, height: 1.3),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          Divider(height: 1, indent: 20, endIndent: 20, color: AppColors.border),
          const SizedBox(height: 12),
          for (var i = 0; i < _dests.length; i++)
            _NavItem(
              icon: selected == i ? _dests[i].selectedIcon : _dests[i].icon,
              label: _dests[i].label,
              selected: selected == i,
              onTap: () => onSelect(i),
            ),
          const Spacer(),
          _NavItem(
            icon: Icons.settings_outlined,
            label: 'Settings',
            onTap: () => _push(context, const SettingsScreen()),
          ),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 4, 24, 20),
            child: Text('CareerPilot AI · v1.0', style: TextStyle(fontSize: 11, color: AppColors.textFaint)),
          ),
        ],
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({required this.icon, required this.label, required this.onTap, this.selected = false});
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final colour = selected ? AppColors.brand : AppColors.textMuted;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      child: Material(
        color: selected ? AppColors.brandTint : Colors.transparent,
        borderRadius: BorderRadius.circular(AppSizes.radius),
        child: InkWell(
          borderRadius: BorderRadius.circular(AppSizes.radius),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              children: [
                Icon(icon, size: 21, color: colour),
                const SizedBox(width: 14),
                Text(
                  label,
                  style: TextStyle(
                    color: selected ? AppColors.brand : AppColors.text,
                    fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
