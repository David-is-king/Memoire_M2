import 'package:flutter/material.dart';
import 'api_service.dart';
import 'dashboard_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _apiService = ApiService();
  bool _isLoading = false;

  void _handleLogin() async {
    if (_emailController.text.trim().isEmpty || _passwordController.text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Veuillez remplir tous les champs')),
      );
      return;
    }

    setState(() => _isLoading = true);
    
    final success = await _apiService.login(
      _emailController.text.trim(),
      _passwordController.text,
    );

    setState(() => _isLoading = false);

    if (success && mounted) {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const DashboardScreen()),
      );
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Email ou mot de passe incorrect')),
      );
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white, // Fond blanc comme sur la maquette
      body: SingleChildScrollView(
        child: Column(
          children: [
            // Section supérieure avec l'image courbée et le bouton de fermeture
            Stack(
              clipBehavior: Clip.none,
              alignment: Alignment.bottomCenter,
              children: [
                ClipPath(
                  clipper: CurveClipper(),
                  child: Container(
                    height: MediaQuery.of(context).size.height * 0.38,
                    width: double.infinity,
                    decoration: const BoxDecoration(
                      image: DecorationImage(
                        // N'oubliez pas d'ajouter une image de plantes dans vos assets ou d'utiliser une image réseau temporaire
                        image: NetworkImage('https://images.unsplash.com/photo-1545241047-6083a3684587?q=80&w=1000'), 
                        fit: BoxFit.cover,
                      ),
                    ),
                    child: Container(
                      color: Colors.black.withValues(alpha: 0.25), // Filtre pour lisibilité
                      padding: const EdgeInsets.symmetric(horizontal: 24.0),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: const [
                          Text(
                            'SmartPredict',
                            style: TextStyle(
                              fontFamily: 'Serif',
                              fontSize: 36,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                          SizedBox(height: 2),
                          Text(
                            '____________________',
                            style: TextStyle(color: Colors.white54),
                          ),
                          SizedBox(height: 12),
                          Text(
                            'Maintenance prédictive intelligente.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 13,
                              color: Colors.white70,
                              fontStyle: FontStyle.italic,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                // Bouton de fermeture (X) au centre de la courbe
                Positioned(
                  bottom: -22,
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.1),
                          spreadRadius: 1,
                          blurRadius: 6,
                          offset: const Offset(0, 3),
                        ),
                      ],
                    ),
                    child: IconButton(
                      icon: const Icon(Icons.close, color: Colors.black54, size: 22),
                      onPressed: () {
                        // Action de fermeture ou retour si nécessaire
                      },
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 45),

            // Section Formulaire d'authentification
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32.0),
              child: Column(
                children: [
                  const Text(
                    'Bienvenue!',
                    style: TextStyle(
                      fontFamily: 'Serif',
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      color: Color(0xFF1B4D22), // Vert foncé de la maquette
                    ),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'connectez-vous pour continuer',
                    style: TextStyle(color: Colors.black38, fontSize: 14),
                  ),
                  const SizedBox(height: 35),

                  // Champ Email
                  TextField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    style: const TextStyle(color: Colors.black87),
                    decoration: InputDecoration(
                      hintText: 'Email',
                      hintStyle: const TextStyle(color: Colors.black38),
                      suffixIcon: const Icon(Icons.email_outlined, color: Color(0xFF1B4D22)),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(15.0),
                        borderSide: const BorderSide(color: Colors.black26),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(15.0),
                        borderSide: const BorderSide(color: Color(0xFF1B4D22), width: 1.5),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // Champ Mot de passe
                  TextField(
                    controller: _passwordController,
                    obscureText: true,
                    style: const TextStyle(color: Colors.black87),
                    decoration: InputDecoration(
                      hintText: 'Mot de passe',
                      hintStyle: const TextStyle(color: Colors.black38),
                      suffixIcon: const Icon(Icons.lock_outline, color: Color(0xFF1B4D22)),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(15.0),
                        borderSide: const BorderSide(color: Colors.black26),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(15.0),
                        borderSide: const BorderSide(color: Color(0xFF1B4D22), width: 1.5),
                      ),
                    ),
                  ),
                  
                  // Mot de passe oublié
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton(
                      onPressed: () {},
                      child: const Text(
                        'Mot de passe oublié ?',
                        style: TextStyle(color: Colors.black45, fontSize: 13),
                      ),
                    ),
                  ),
                  const SizedBox(height: 15),

                  // Bouton LOGIN avec état de chargement intégré
                  SizedBox(
                    width: double.infinity,
                    height: 52,
                    child: ElevatedButton(
                      onPressed: _isLoading ? null : _handleLogin,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF2E7D32), // Vert forêt
                        disabledBackgroundColor: const Color(0xFF2E7D32).withValues(alpha: 0.6),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(15.0),
                        ),
                        elevation: 2,
                      ),
                      child: _isLoading
                          ? const SizedBox(
                              height: 24,
                              width: 24,
                              child: CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 2.5,
                              ),
                            )
                          : const Text(
                              'Se connecter',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                                letterSpacing: 1,
                              ),
                            ),
                    ),
                  ),
                  const SizedBox(height: 30),

                  // Lien d'inscription (Register Now)
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Text("Accès sécurisé aux systèmes industriels", style: TextStyle(color: Colors.black45)),
                      GestureDetector(
                        onTap: () {},
                        child: const Text(
                          'Register Now',
                          style: TextStyle(
                            color: Color(0xFF1B4D22),
                            fontWeight: FontWeight.bold,
                            decoration: TextDecoration.underline,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// Outil de découpe personnalisé pour réaliser l'arche inversée de l'image en haut
class CurveClipper extends CustomClipper<Path> {
  @override
  Path getClip(Size size) {
    Path path = Path();
    path.lineTo(0, size.height - 50);
    
    // Le point de contrôle au milieu de la largeur, poussé vers le bas pour accentuer la courbure
    var controlPoint = Offset(size.width / 2, size.height + 15);
    var endPoint = Offset(size.width, size.height - 50);
    
    path.quadraticBezierTo(controlPoint.dx, controlPoint.dy, endPoint.dx, endPoint.dy);
    path.lineTo(size.width, 0);
    path.close();
    return path;
  }

  @override
  bool shouldReclip(CustomClipper<Path> oldClipper) => false;
}
