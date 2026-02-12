<?php
error_reporting(E_ALL & ~E_WARNING & ~E_NOTICE & ~E_DEPRECATED);
function adminer_object() {
    class AdminerSoftware extends Adminer {
        function login($login, $password) {
            return true;
        }
    }
    return new AdminerSoftware;
}
include "./adminer.php";

