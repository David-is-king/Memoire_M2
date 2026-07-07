import 'package:flutter/material.dart';

class AppTheme {
  // Couleurs principales - Bleu marine professionnel
  static const Color primary = Color(0xFF1565C0);       // Bleu marine
  static const Color primaryDark = Color(0xFF0D3B8E);   // Bleu foncé
  static const Color primaryLight = Color(0xFF1976D2);  // Bleu moyen
  static const Color accent = Color(0xFF2196F3);        // Bleu clair accent

  // Backgrounds
  static const Color background = Color(0xFFF4F6F8);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceElevated = Color(0xFFF8F9FA);
  static const Color headerBg = Color(0xFF0D3B8E);      // Header bleu foncé

  // Bordures
  static const Color border = Color(0xFFE0E5EC);

  // Statuts
  static const Color danger = Color(0xFFE53935);        // Rouge critique
  static const Color dangerBg = Color(0xFFFFEBEE);
  static const Color warning = Color(0xFFFF6F00);       // Orange alerte
  static const Color warningBg = Color(0xFFFFF3E0);
  static const Color success = Color(0xFF2E7D32);       // Vert OK
  static const Color successBg = Color(0xFFE8F5E9);
  static const Color info = Color(0xFF0277BD);          // Bleu info
  static const Color infoBg = Color(0xFFE1F5FE);

  // Textes
  static const Color textPrimary = Color(0xFF1A2340);
  static const Color textSecondary = Color(0xFF607D9C);
  static const Color textMuted = Color(0xFFB0BEC5);
  static const Color textOnPrimary = Color(0xFFFFFFFF);

  // Couleurs legacy pour compatibilité websocket_service etc.
  static const Color accentDim = Color(0xFFE3F2FD);
  static const Color primaryDim = Color(0xFFE3F2FD);
  static const Color dangerDim = Color(0xFFFFEBEE);
  static const Color warningDim = Color(0xFFFFF3E0);

  static ThemeData get darkTheme => lightTheme;

  static ThemeData get lightTheme {
    return ThemeData(
      brightness: Brightness.light,
      scaffoldBackgroundColor: background,
      colorScheme: const ColorScheme.light(
        primary: primary,
        secondary: accent,
        surface: surface,
        error: danger,
      ),
      fontFamily: 'Roboto',
      appBarTheme: const AppBarTheme(
        backgroundColor: headerBg,
        elevation: 0,
        iconTheme: IconThemeData(color: textOnPrimary),
        titleTextStyle: TextStyle(
          color: textOnPrimary,
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: surface,
        selectedItemColor: primary,
        unselectedItemColor: textMuted,
        type: BottomNavigationBarType.fixed,
        elevation: 8,
      ),
      useMaterial3: true,
    );
  }
}

class AppTextStyles {
  static const TextStyle displayLarge = TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.w700,
    color: AppTheme.textPrimary,
    letterSpacing: -0.5,
  );

  static const TextStyle headingMedium = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w600,
    color: AppTheme.textPrimary,
  );

  static const TextStyle headingSmall = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    color: AppTheme.textPrimary,
  );

  static const TextStyle labelMono = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    color: AppTheme.textSecondary,
    letterSpacing: 0.5,
  );

  static const TextStyle valueLarge = TextStyle(
    fontSize: 32,
    fontWeight: FontWeight.w700,
    color: AppTheme.primary,
    letterSpacing: -1,
  );

  static const TextStyle valueSmall = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w700,
    color: AppTheme.textPrimary,
  );

  static const TextStyle bodyText = TextStyle(
    fontSize: 13,
    color: AppTheme.textSecondary,
    height: 1.4,
  );
}
