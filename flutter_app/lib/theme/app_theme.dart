import 'package:flutter/material.dart';

class AppColors {
  static const Color primary      = Color(0xFF2563EB);
  static const Color primaryLight = Color(0xFFEFF6FF);
  static const Color primaryMid   = Color(0xFFBFDBFE);
  static const Color bg           = Color(0xFFF5F7FA);
  static const Color surface      = Color(0xFFFFFFFF);
  static const Color textDark     = Color(0xFF0F172A);
  static const Color textMid      = Color(0xFF475569);
  static const Color textLight    = Color(0xFF94A3B8);
  static const Color border       = Color(0xFFE2E8F0);
  static const Color healthy      = Color(0xFF16A34A);
  static const Color healthyBg    = Color(0xFFDCFCE7);
  static const Color warning      = Color(0xFFD97706);
  static const Color warningBg    = Color(0xFFFEF3C7);
  static const Color critical     = Color(0xFFDC2626);
  static const Color criticalBg   = Color(0xFFFFEEEE);
  static const Color info         = Color(0xFF0891B2);
  static const Color infoBg       = Color(0xFFE0F7FA);
}

class AppText {
  static const String font = 'Nunito';
  static const h1   = TextStyle(fontFamily: font, fontSize: 26, fontWeight: FontWeight.w800, color: AppColors.textDark, letterSpacing: -0.5);
  static const h2   = TextStyle(fontFamily: font, fontSize: 18, fontWeight: FontWeight.w700, color: AppColors.textDark);
  static const h3   = TextStyle(fontFamily: font, fontSize: 15, fontWeight: FontWeight.w700, color: AppColors.textDark);
  static const body = TextStyle(fontFamily: font, fontSize: 13, fontWeight: FontWeight.w500, color: AppColors.textMid, height: 1.4);
  static const sm   = TextStyle(fontFamily: font, fontSize: 11, fontWeight: FontWeight.w400, color: AppColors.textLight);
  static const numB = TextStyle(fontFamily: font, fontSize: 36, fontWeight: FontWeight.w800, color: AppColors.textDark, letterSpacing: -1);
  static const numM = TextStyle(fontFamily: font, fontSize: 20, fontWeight: FontWeight.w700, color: AppColors.textDark);
}

List<BoxShadow> cardShadow() => [BoxShadow(color: const Color(0xFF0F172A).withOpacity(0.07), blurRadius: 20, offset: const Offset(0, 4))];
List<BoxShadow> blueShadow() => [BoxShadow(color: AppColors.primary.withOpacity(0.30), blurRadius: 20, offset: const Offset(0, 8))];

class AppTheme {
  static ThemeData get light => ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    scaffoldBackgroundColor: AppColors.bg,
    colorScheme: ColorScheme.fromSeed(seedColor: AppColors.primary),
    appBarTheme: const AppBarTheme(backgroundColor: AppColors.bg, elevation: 0, scrolledUnderElevation: 0, iconTheme: IconThemeData(color: AppColors.textDark)),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: AppColors.surface, selectedItemColor: AppColors.primary,
      unselectedItemColor: AppColors.textLight, type: BottomNavigationBarType.fixed, elevation: 0,
    ),
  );
}