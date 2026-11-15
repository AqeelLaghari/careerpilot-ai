import 'package:flutter/material.dart';

import '../widgets/account_menu.dart';
import '../widgets/brand.dart';
import 'career/career_screen.dart';
import 'dashboard_screen.dart';
import 'interview/interview_screen.dart';
import 'jobs/jobs_screen.dart';
import 'resume/resume_screen.dart';

/// The main app frame after login: a top bar plus bottom navigation tabs.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _tab = 0;

  final _pages = const [DashboardScreen(), ResumeScreen(), CareerScreen(), JobsScreen(), InterviewScreen()];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const BrandLogo.horizontal(size: 30, white: true),
        actions: const [AccountMenu(), SizedBox(width: 8)],
      ),
      body: _pages[_tab],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dashboard), label: 'Dashboard'),
          NavigationDestination(icon: Icon(Icons.description), label: 'Resume'),
          NavigationDestination(icon: Icon(Icons.explore), label: 'Career'),
          NavigationDestination(icon: Icon(Icons.work_outline), label: 'Jobs'),
          NavigationDestination(icon: Icon(Icons.videocam), label: 'Interview'),
        ],
      ),
    );
  }
}
