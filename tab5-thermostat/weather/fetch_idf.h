// One HTTPS GET at a time, in its own FreeRTOS task (ESP-IDF only). ESPHome's http_request actions
// run on the main loop, so DNS, connecting and TLS (each up to its timeout, much longer with the
// internet down) would pause the screen and the thermostat, and log "took a long time" each poll.
// Here the main loop only starts a fetch and later collects the result.
#pragma once

#include <atomic>
#include <cstddef>
#include <string>

#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace chestnut_weather {

class Fetch {
 public:
  static constexpr size_t MAX_BODY = 4096;   // the reply is ~400 bytes; past this the poll fails
  static constexpr int TIMEOUT_MS = 10000;   // esp_http_client's, per connect / read
  static constexpr uint32_t STACK = 10240;   // TLS handshake; the high-water mark is logged

  // Starts a GET of url. False if a fetch is still running or the task couldn't start.
  bool start(const std::string &url) {
    if (state_.load() != IDLE) return false;
    url_ = url;
    body_.clear();
    status_ = -1;
    overflow_ = false;
    state_.store(RUNNING);
    if (xTaskCreate(&Fetch::task_, "weather", STACK, this, tskIDLE_PRIORITY + 1, nullptr) != pdPASS) {
      state_.store(IDLE);
      return false;
    }
    return true;
  }

  // Once the fetch has finished: true, with the HTTP status (-1: no reply), the body, and whether it
  // overflowed MAX_BODY (then parts were dropped: chestnut_weather::reading_from refuses it).
  bool finished(int *status, std::string *body, bool *overflow, uint32_t *stack_free = nullptr) {
    if (state_.load() != DONE) return false;
    *status = status_;
    *body = std::move(body_);
    *overflow = overflow_;
    if (stack_free) *stack_free = stack_free_;
    state_.store(IDLE);
    return true;
  }

 private:
  enum : int { IDLE, RUNNING, DONE };

  static esp_err_t on_event_(esp_http_client_event_t *e) {
    auto *f = static_cast<Fetch *>(e->user_data);
    if (e->event_id != HTTP_EVENT_ON_DATA || e->data_len <= 0 || f->overflow_) return ESP_OK;
    // Once a piece is dropped, every later one is too: the body never has a hole in the middle.
    if (f->body_.size() + e->data_len > MAX_BODY) f->overflow_ = true;
    else f->body_.append(static_cast<const char *>(e->data), e->data_len);
    return ESP_OK;
  }

  static void task_(void *arg) {
    auto *f = static_cast<Fetch *>(arg);
    esp_http_client_config_t cfg = {};
    cfg.url = f->url_.c_str();
    cfg.timeout_ms = TIMEOUT_MS;
    cfg.crt_bundle_attach = esp_crt_bundle_attach;
    cfg.event_handler = &Fetch::on_event_;
    cfg.user_data = f;
    cfg.buffer_size = 1024;
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    if (c != nullptr) {
      if (esp_http_client_perform(c) == ESP_OK) f->status_ = esp_http_client_get_status_code(c);
      esp_http_client_cleanup(c);
    }
    f->stack_free_ = uxTaskGetStackHighWaterMark(nullptr) * sizeof(StackType_t);
    f->state_.store(DONE);  // after every write above: the main loop reads them once it sees DONE
    vTaskDelete(nullptr);
  }

  std::atomic<int> state_{IDLE};
  std::string url_;
  std::string body_;
  int status_ = -1;
  bool overflow_ = false;
  uint32_t stack_free_ = 0;
};

inline Fetch &fetch() {
  static Fetch f;
  return f;
}

}  // namespace chestnut_weather
