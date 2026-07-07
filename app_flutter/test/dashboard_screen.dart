import 'package:flutter/material.dart';
import 'package:app_flutter/app_theme.dart';
import 'package:app_flutter/alerts_screen.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        title: const Text('DASHBOARD', style: AppTextStyles.headingMedium),
        backgroundColor: AppTheme.background,
        actions: [
          IconButton(
            icon: const Icon(Icons.notifications_none_rounded, color: AppTheme.primary),
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const AlertsScreen()),
            ),
          ),
        ],
      ),
      body: const Center(
        child: Text(
          'Système de Maintenance Prédictive',
          style: TextStyle(color: AppTheme.textSecondary),
        ),
      ),
    );
  }
}
