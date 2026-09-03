// ─────────────────────────────────────────────
// screens/profile_screen.dart
// Ecran 10 : Profil / Paramètres
// ─────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'app_theme.dart';
import 'login_screen.dart';
import 'current_user.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(title: const Text('Profil')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Center(
            child: Column(
              children: [
                const CircleAvatar(
                  radius: 40,
                  backgroundColor: AppTheme.primary,
                  child: Icon(Icons.engineering_rounded, color: Colors.white, size: 36),
                ),
                const SizedBox(height: 12),
                Text(CurrentUser.displayName, style: AppTextStyles.headingMedium),
                const SizedBox(height: 2),
                Text(CurrentUser.roleLabel, style: AppTextStyles.labelMono.copyWith(fontSize: 12)),
                const SizedBox(height: 8),
                Text(CurrentUser.email ?? '', style: AppTextStyles.bodyText.copyWith(fontSize: 12)),
              ],
            ),
          ),
          const SizedBox(height: 28),
          _MenuTile(icon: Icons.person_outline_rounded, label: 'Informations personnelles', onTap: () {}),
          _MenuTile(icon: Icons.tune_rounded, label: 'Préférences', onTap: () {}),
          _MenuTile(icon: Icons.lock_outline_rounded, label: 'Sécurité', onTap: () {}),
          _MenuTile(icon: Icons.info_outline_rounded, label: 'À propos', onTap: () {}),
          const SizedBox(height: 12),
          _MenuTile(
            icon: Icons.logout_rounded,
            label: 'Déconnexion',
            color: AppTheme.danger,
            onTap: () {
              CurrentUser.clear();
              Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (_) => const LoginScreen()),
                (route) => false,
              );
            },
          ),
        ],
      ),
    );
  }
}

class _MenuTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color? color;
  final VoidCallback onTap;

  const _MenuTile({required this.icon, required this.label, required this.onTap, this.color});

  @override
  Widget build(BuildContext context) {
    final c = color ?? AppTheme.textPrimary;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      child: ListTile(
        leading: Icon(icon, color: c, size: 20),
        title: Text(label, style: TextStyle(color: c, fontSize: 14, fontWeight: FontWeight.w500)),
        trailing: Icon(Icons.chevron_right_rounded, color: AppTheme.textMuted, size: 20),
        onTap: onTap,
      ),
    );
  }
}
