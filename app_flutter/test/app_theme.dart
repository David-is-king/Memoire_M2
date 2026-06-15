import 'package:flutter/material.dart';

class AppTheme {
  static const Color background = Color(0xFF0F0F0F);
  static const Color primary = Color(0xFF00E5FF);
  static const Color surface = Color(0xFF1E1E1E);
  static const Color surfaceElevated = Color(0xFF2C2C2C);
  static const Color border = Color(0xFF333333);
  static const Color danger = Color(0xFFFF5252);
  static const Color warning = Color(0xFFFFAB40);
  static const Color textPrimary = Color(0xFFFFFFFF);
  static const Color textSecondary = Color(0xFFB0B0B0);
  static const Color textMuted = Color(0xFF666666);

  static final ThemeData darkTheme = ThemeData.dark().copyWith(
    scaffoldBackgroundColor: background,
    colorScheme: const ColorScheme.dark(
      primary: primary,
      surface: surface,
      error: danger,
    ),
  );
}

class AppTextStyles {
  static const TextStyle headingMedium = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.bold,
    color: AppTheme.textPrimary,
  );
  static const TextStyle labelMono = TextStyle(
    fontFamily: 'monospace',
    fontSize: 11,
    color: AppTheme.textSecondary,
  );
}