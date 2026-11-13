//! Minimal C API over WebRTC's AudioProcessing echo canceller (AEC3), for nexora-audio.
//!
//! WebRTC AudioProcessing (BSD-3, Google), built from the `webrtc-audio-processing` crate's
//! bundled source (v2.1). Only the echo canceller is enabled: noise suppression, gain control
//! and the rest stay in nexora-audio's own pipeline.
//!
//! Frames are 10 ms of mono float32 audio in [-1, 1] at the rate given to `nexora_aec_create`
//! (8, 16, 32 or 48 kHz).

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr::null_mut;
use std::slice;

use webrtc_audio_processing::config::{Config, EchoCanceller};
use webrtc_audio_processing::experimental::EchoCanceller3Config;
use webrtc_audio_processing::Processor;

pub struct NexoraAec {
    processor: Processor,
    frame: usize,
}

/// Create an echo canceller. `stream_delay_ms` < 0 lets AEC3 estimate the delay itself.
/// Returns null on failure.
#[no_mangle]
pub extern "C" fn nexora_aec_create(sample_rate: u32, stream_delay_ms: i32) -> *mut NexoraAec {
    let made = catch_unwind(|| {
        let processor = Processor::new(sample_rate).ok()?;
        let delay = if stream_delay_ms < 0 { None } else { Some(stream_delay_ms as u16) };
        processor.set_config(Config {
            echo_canceller: Some(EchoCanceller::Full { stream_delay_ms: delay }),
            ..Default::default()
        });
        let frame = processor.num_samples_per_frame();
        Some(Box::into_raw(Box::new(NexoraAec { processor, frame })))
    });
    match made {
        Ok(Some(p)) => p,
        _ => null_mut(),
    }
}

/// Number of tuning values `nexora_aec_create_tuned` reads.
pub const NEXORA_AEC_TUNING_LEN: usize = 12;

/// Create an echo canceller with AEC3 tuning. `tuning` holds `NEXORA_AEC_TUNING_LEN` values
/// (NaN keeps WebRTC's default), in this order:
///  0 ep_strength.default_gain            1 ep_strength.default_len
///  2 normal_tuning.mask_lf.enr_transparent   3 normal_tuning.mask_lf.enr_suppress
///  4 normal_tuning.mask_hf.enr_transparent   5 normal_tuning.mask_hf.enr_suppress
///  6 dominant_nearend_detection.enr_threshold 7 dominant_nearend_detection.snr_threshold
///  8 dominant_nearend_detection.hold_duration 9 dominant_nearend_detection.trigger_threshold
/// 10 nearend_tuning.mask_lf.enr_transparent 11 nearend_tuning.mask_lf.enr_suppress
/// The configuration is validated (clamped to WebRTC's ranges). Returns null on failure.
#[no_mangle]
pub extern "C" fn nexora_aec_create_tuned(
    sample_rate: u32,
    stream_delay_ms: i32,
    tuning: *const f32,
) -> *mut NexoraAec {
    if tuning.is_null() {
        return nexora_aec_create(sample_rate, stream_delay_ms);
    }
    let t = unsafe { slice::from_raw_parts(tuning, NEXORA_AEC_TUNING_LEN) }.to_vec();
    let made = catch_unwind(move || {
        let mut c = EchoCanceller3Config::default();
        let set = |v: f32, f: &mut f32| {
            if !v.is_nan() {
                *f = v
            }
        };
        set(t[0], &mut c.ep_strength.default_gain);
        set(t[1], &mut c.ep_strength.default_len);
        set(t[2], &mut c.suppressor.normal_tuning.mask_lf.enr_transparent);
        set(t[3], &mut c.suppressor.normal_tuning.mask_lf.enr_suppress);
        set(t[4], &mut c.suppressor.normal_tuning.mask_hf.enr_transparent);
        set(t[5], &mut c.suppressor.normal_tuning.mask_hf.enr_suppress);
        set(t[6], &mut c.suppressor.dominant_nearend_detection.enr_threshold);
        set(t[7], &mut c.suppressor.dominant_nearend_detection.snr_threshold);
        if !t[8].is_nan() {
            c.suppressor.dominant_nearend_detection.hold_duration = t[8] as i32;
        }
        if !t[9].is_nan() {
            c.suppressor.dominant_nearend_detection.trigger_threshold = t[9] as i32;
        }
        set(t[10], &mut c.suppressor.nearend_tuning.mask_lf.enr_transparent);
        set(t[11], &mut c.suppressor.nearend_tuning.mask_lf.enr_suppress);
        c.validate();
        let processor = Processor::with_aec3_config(sample_rate, c).ok()?;
        let delay = if stream_delay_ms < 0 { None } else { Some(stream_delay_ms as u16) };
        processor.set_config(Config {
            echo_canceller: Some(EchoCanceller::Full { stream_delay_ms: delay }),
            ..Default::default()
        });
        let frame = processor.num_samples_per_frame();
        Some(Box::into_raw(Box::new(NexoraAec { processor, frame })))
    });
    match made {
        Ok(Some(p)) => p,
        _ => null_mut(),
    }
}

/// Samples per 10 ms frame.
#[no_mangle]
pub extern "C" fn nexora_aec_frame_size(aec: *const NexoraAec) -> usize {
    if aec.is_null() {
        return 0;
    }
    unsafe { (*aec).frame }
}

/// Feed 10 ms of the far-end (agent / playback) audio. Returns 0 on success.
#[no_mangle]
pub extern "C" fn nexora_aec_render(aec: *mut NexoraAec, samples: *const f32) -> i32 {
    if aec.is_null() || samples.is_null() {
        return -1;
    }
    let r = catch_unwind(AssertUnwindSafe(|| unsafe {
        let a = &*aec;
        let frame = slice::from_raw_parts(samples, a.frame);
        a.processor.analyze_render_frame([frame]).is_ok()
    }));
    if matches!(r, Ok(true)) { 0 } else { -2 }
}

/// Remove echo from 10 ms of near-end (microphone / caller) audio, in place. 0 on success.
#[no_mangle]
pub extern "C" fn nexora_aec_capture(aec: *mut NexoraAec, samples: *mut f32) -> i32 {
    if aec.is_null() || samples.is_null() {
        return -1;
    }
    let r = catch_unwind(AssertUnwindSafe(|| unsafe {
        let a = &*aec;
        let frame = slice::from_raw_parts_mut(samples, a.frame);
        a.processor.process_capture_frame([frame]).is_ok()
    }));
    if matches!(r, Ok(true)) { 0 } else { -2 }
}

/// Statistics of the last capture frame: [ERLE dB, ERL dB, delay ms, residual echo
/// likelihood]; NaN where not available.
#[no_mangle]
pub extern "C" fn nexora_aec_stats(aec: *const NexoraAec, out: *mut f64) -> i32 {
    if aec.is_null() || out.is_null() {
        return -1;
    }
    let s = unsafe { (*aec).processor.get_stats() };
    let vals = [
        s.echo_return_loss_enhancement.unwrap_or(f64::NAN),
        s.echo_return_loss.unwrap_or(f64::NAN),
        s.delay_ms.map(f64::from).unwrap_or(f64::NAN),
        s.residual_echo_likelihood.unwrap_or(f64::NAN),
    ];
    unsafe { slice::from_raw_parts_mut(out, 4).copy_from_slice(&vals) };
    0
}

#[no_mangle]
pub extern "C" fn nexora_aec_destroy(aec: *mut NexoraAec) {
    if !aec.is_null() {
        unsafe { drop(Box::from_raw(aec)) };
    }
}
