import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'firebase_options.dart';

class FirebaseWorkspace {
  FirebaseWorkspace._();
  static final instance = FirebaseWorkspace._();

  bool initialized = false;
  String status = 'Firebase project configuration required';
  FirebaseAuth? _auth;
  FirebaseFirestore? _store;
  FirebaseMessaging? _messaging;
  StreamSubscription<RemoteMessage>? _foregroundSubscription;
  StreamSubscription<String>? _tokenSubscription;
  StreamSubscription<RemoteMessage>? _openedSubscription;

  /// Latest FCM registration token, if push registration completed.
  String? pushToken;

  /// Called with every fresh FCM token (initial registration and refreshes)
  /// so the app can register it with the local backend. Never throws.
  void Function(String token)? onPushToken;

  void _emitPushToken(String? token) {
    if (token == null || token.isEmpty) return;
    pushToken = token;
    try {
      onPushToken?.call(token);
    } catch (_) {
      // Registration with the backend is best-effort.
    }
  }

  Future<void> initialize() async {
    if (!OneBoardFirebaseOptions.isConfigured) return;
    try {
      await Firebase.initializeApp(
        options: OneBoardFirebaseOptions.currentPlatform,
      );
      _auth = FirebaseAuth.instance;
      _store = FirebaseFirestore.instance;
      _messaging = FirebaseMessaging.instance;
      initialized = true;
      status = 'Firebase connected';
    } catch (error) {
      status = 'Firebase unavailable: $error';
    }
  }

  Future<void> attachForegroundMessages(
    void Function(String title, String body) onMessage, {
    void Function(RemoteMessage message)? onOpen,
  }) async {
    if (!initialized) return;
    await _foregroundSubscription?.cancel();
    await _openedSubscription?.cancel();
    _foregroundSubscription = FirebaseMessaging.onMessage.listen((message) {
      onMessage(
        message.notification?.title ?? 'ONEBoard',
        message.notification?.body ?? 'You have a new notification.',
      );
    });
    if (onOpen != null) {
      _openedSubscription = FirebaseMessaging.onMessageOpenedApp.listen(onOpen);
      final initial = await FirebaseMessaging.instance.getInitialMessage();
      if (initial != null) onOpen(initial);
    }
  }

  /// Human-readable push status for diagnostics. Real delivery additionally
  /// requires an APNs key in Firebase and a provisioning profile with push.
  String get pushStatus => status;

  Future<void> registerUser(
    String email,
    String password,
    Map<String, dynamic> profile,
  ) async {
    if (!initialized) return;
    try {
      UserCredential credential;
      try {
        credential = await _auth!.signInWithEmailAndPassword(
          email: email,
          password: password,
        );
      } on FirebaseAuthException catch (error) {
        if (![
          'user-not-found',
          'invalid-credential',
          'wrong-password',
        ].contains(error.code)) {
          rethrow;
        }
        credential = await _auth!.createUserWithEmailAndPassword(
          email: email,
          password: password,
        );
      }
      final user = credential.user;
      if (user == null) return;
      await _store!.collection('users').doc(user.uid).set({
        'email': email,
        'name': profile['name'] ?? '',
        'lastSeenAt': FieldValue.serverTimestamp(),
        'platform': 'macos',
      }, SetOptions(merge: true));
      await _tokenSubscription?.cancel();
      _tokenSubscription = _messaging!.onRegistered.listen((token) {
        _store!
            .collection('users')
            .doc(user.uid)
            .collection('devices')
            .doc('macos')
            .set({
              'token': token,
              'platform': 'macos',
              'updatedAt': FieldValue.serverTimestamp(),
            }, SetOptions(merge: true));
        _emitPushToken(token);
      });
      await _registerPushToken();
      status = 'Firebase connected';
    } catch (error) {
      status = 'ONEBoard data connected; Firebase: $error';
    }
  }

  Future<void> _registerPushToken() async {
    try {
      final permission = await _messaging!.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );
      if (permission.authorizationStatus == AuthorizationStatus.denied) {
        status = 'Firebase connected; macOS notifications are disabled';
        return;
      }
      await _messaging!.register();
      status = 'Push notifications enabled';
      // The current token arrives through onRegistered, which also feeds
      // the Firestore device record and _emitPushToken.
    } catch (error) {
      status = 'Firebase connected; push is waiting for APNs: $error';
    }
  }

  Future<void> cacheNotifications(List<dynamic> notifications) async {
    final user = _auth?.currentUser;
    if (user == null || _store == null) return;
    final collection = _store!
        .collection('users')
        .doc(user.uid)
        .collection('notifications');
    final batch = _store!.batch();
    for (final item in notifications) {
      if (item is! Map) continue;
      final id = item['id']?.toString();
      if (id == null || id.isEmpty) continue;
      batch.set(collection.doc(id), {
        ...item.cast<String, dynamic>(),
        'syncedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));
    }
    if (notifications.isNotEmpty) await batch.commit();
  }

  Future<void> cacheSnapshot(String key, Map<String, dynamic> data) async {
    final user = _auth?.currentUser;
    if (user == null || _store == null) return;
    await _store!
        .collection('users')
        .doc(user.uid)
        .collection('appData')
        .doc(key)
        .set({
          'data': data,
          'syncedAt': FieldValue.serverTimestamp(),
        }, SetOptions(merge: true));
  }

  Future<Map<String, dynamic>?> readSnapshot(String key) async {
    final user = _auth?.currentUser;
    if (user == null || _store == null) return null;
    final snapshot = await _store!
        .collection('users')
        .doc(user.uid)
        .collection('appData')
        .doc(key)
        .get();
    final value = snapshot.data()?['data'];
    return value is Map ? value.cast<String, dynamic>() : null;
  }

  Future<void> signOut() async {
    if (!initialized) return;
    await _auth?.signOut();
  }
}
