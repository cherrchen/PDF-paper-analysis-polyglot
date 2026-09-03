//! Core PDF primitives. Product parsing is not implemented yet.

/// Workspace liveness helper used by bootstrap tests.
#[must_use]
pub fn crate_status() -> &'static str {
    "ok"
}

#[cfg(test)]
mod tests {
    use super::crate_status;

    #[test]
    fn status_is_ok() {
        assert_eq!(crate_status(), "ok");
    }
}
