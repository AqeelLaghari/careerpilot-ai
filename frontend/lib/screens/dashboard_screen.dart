import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../services/api_client.dart';

/// Shows what the backend knows about the user (their Blackboard state).
/// For now this just proves the app ↔ backend ↔ Firebase connection works.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late Future<Map<String, dynamic>> _me = api.get('/me');

  @override
  Widget build(BuildContext context) {
    final user = FirebaseAuth.instance.currentUser;
    return RefreshIndicator(
      onRefresh: () async => setState(() => _me = api.get('/me')),
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('Welcome, ${user?.displayName ?? user?.email ?? ''}',
              style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 16),
          FutureBuilder<Map<String, dynamic>>(
            future: _me,
            builder: (context, snap) {
              if (snap.connectionState != ConnectionState.done) {
                return const Center(child: CircularProgressIndicator());
              }
              if (snap.hasError) {
                return Card(
                  color: Theme.of(context).colorScheme.errorContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text('Could not reach backend.\nIs uvicorn running?\n\n${snap.error}'),
                  ),
                );
              }
              final data = snap.data!;
              return Card(
                child: ListTile(
                  leading: const Icon(Icons.check_circle, color: Colors.green),
                  title: const Text('Connected to CareerPilot backend'),
                  subtitle: Text('User ID: ${data['uid']}\n'
                      'Sections saved: ${(data['state'] as Map).keys.where((k) => !k.startsWith('_')).join(', ').ifEmpty('none yet')}'),
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}

extension on String {
  String ifEmpty(String fallback) => isEmpty ? fallback : this;
}
