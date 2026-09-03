// ─────────────────────────────────────────────
// current_user.dart
// Etat global minimal de l'utilisateur connecte,
// rempli a partir de la reponse /auth/login.
// ─────────────────────────────────────────────

class CurrentUser {
  static String? id;
  static String? email;
  static String? fullName;
  static String? role;

  static void set({
    required String id,
    required String email,
    String? fullName,
    String? role,
  }) {
    CurrentUser.id = id;
    CurrentUser.email = email;
    CurrentUser.fullName = fullName;
    CurrentUser.role = role;
  }

  static void clear() {
    id = null;
    email = null;
    fullName = null;
    role = null;
  }

  static String get displayName =>
      (fullName != null && fullName!.trim().isNotEmpty) ? fullName! : (email ?? 'Utilisateur');

  static String get firstName => displayName.split(' ').first;

  static String get roleLabel {
    switch (role) {
      case 'admin':
        return 'Administrateur';
      case 'technician':
        return 'Technicien de maintenance';
      default:
        return role ?? '';
    }
  }
}
