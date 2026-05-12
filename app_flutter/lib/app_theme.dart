import 'package:flutter/material.dart';

class AppTheme {
  // Colors
  static const Color background = Color(0xFF0A0E1A);
  static const Color surface = Color(0xFF111827);
  static const Color surfaceElevated = Color(0xFF1A2235);
  static const Color border = Color(0xFF1E2D45);

  static const Color primary = Color(0xFF00D4FF);
  static const Color primaryDim = Color(0xFF0A4060);
  static const Color accent = Color(0xFF00FF88);
  static const Color accentDim = Color(0xFF003322);

  static const Color warning = Color(0xFFFFB800);
  static const Color warningDim = Color(0xFF3D2C00);
  static const Color danger = Color(0xFFFF3B5C);
  static const Color dangerDim = Color(0xFF3D0010);

  static const Color textPrimary = Color(0xFFEAF0FF);
  static const Color textSecondary = Color(0xFF6B7FA3);
  static const Color textMuted = Color(0xFF3A4A6B);

  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: background,
      colorScheme: const ColorScheme.dark(
        primary: primary,
        secondary: accent,
        surface: surface,
        error: danger,
      ),
      fontFamily: 'Courier',
      appBarTheme: const AppBarTheme(
        backgroundColor: background,
        elevation: 0,
        titleTextStyle: TextStyle(
          color: textPrimary,
          fontSize: 16,
          fontWeight: FontWeight.w600,
          letterSpacing: 2,
        ),
        iconTheme: IconThemeData(color: primary),
      ),
      useMaterial3: true,
    );
  }
}

class AppTextStyles {
  static const TextStyle displayLarge = TextStyle(
    fontSize: 36,
    fontWeight: FontWeight.w700,
    color: AppTheme.textPrimary,
    letterSpacing: -0.5,
    height: 1.1,
  );

  static const TextStyle headingMedium = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    color: AppTheme.textPrimary,
    letterSpacing: 1.5,
  );

  static const TextStyle labelMono = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    color: AppTheme.textSecondary,
    letterSpacing: 2,
    fontFamily: 'Courier',
  );

  static const TextStyle valueLarge = TextStyle(
    fontSize: 32,
    fontWeight: FontWeight.w700,
    color: AppTheme.primary,
    letterSpacing: -1,
    fontFamily: 'Courier',
  );

  static const TextStyle valueSmall = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w700,
    color: AppTheme.textPrimary,
    letterSpacing: -0.5,
    fontFamily: 'Courier',
  );
}
