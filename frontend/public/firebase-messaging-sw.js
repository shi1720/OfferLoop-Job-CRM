/* OfferLoop web-push service worker.
 *
 * The Firebase web config arrives base64-encoded in the registration URL's
 * query string (no secrets — it's the same public config the page uses).
 * Messages carry a `notification` payload, which the FCM SDK displays
 * automatically once messaging is initialized. */

/* global importScripts, firebase */
importScripts("https://www.gstatic.com/firebasejs/12.18.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/12.18.0/firebase-messaging-compat.js");

try {
  var params = new URLSearchParams(self.location.search);
  var config = JSON.parse(atob(decodeURIComponent(params.get("config") || "")));
  firebase.initializeApp(config);
  var messaging = firebase.messaging();
  messaging.onBackgroundMessage(function (payload) {
    // notification payloads display automatically; this handler exists so
    // data-only messages never get silently dropped.
    if (!payload.notification && payload.data && payload.data.title) {
      self.registration.showNotification(payload.data.title, { body: payload.data.body || "" });
    }
  });
} catch (err) {
  // No/invalid config in the URL: the worker stays inert rather than broken.
}

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        if ("focus" in list[i]) return list[i].focus();
      }
      return clients.openWindow("/");
    }),
  );
});
