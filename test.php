<?php
// Zpracovani argumentu
$options = getopt('', ['help', 'directory:', 'recursive', 'parse-script:', 'int-script:']);
$directory = '';
$parseScript = 'parse.php';
$intScript = 'interpret.py';
$recursive = $argError = false;
$tests = NULL;
$testCount = 0;
$okTests = 0;

// Funkce pro spusteni jednotlivych testu v adresari
function testFiles($directory)
{
    if ($directory != '/' && substr($directory, -1) != '/')
        $directory .= '/';

    global $parseScript, $intScript, $tests, $testCount, $okTests;

    if (!file_exists($parseScript) || !file_exists($intScript))
        exit(11);

    // Nacteni jednotlivych souboru s koncovkou .src
    $files = explode("\n", shell_exec('ls ' . $directory . ' 2>/dev/null | grep .src'));
    $tmpFile = NULL;
    $returnHelper = NULL;

    // Cyklus, ktery probiha pro kazdy test
    foreach ($files as $file) {
        if ($file == "")
            break;

        $file = explode('.src', $file);
        array_pop($file);
        $file = implode('.src', $file);

        $fileHelper = NULL;

        // Vytvoreni souboru a naplneni predepsanymi hodnotami, pokud jiz neexistuji
        if (!file_exists($directory . $file . '.in')) {
            $fileHelper = fopen($directory . $file . '.in', 'w');
            fclose($fileHelper);
        } if (!file_exists($directory . $file . '.out')) {
            $fileHelper = fopen($directory . $file . '.out', 'w');
            fclose($fileHelper);
        } if (!file_exists($directory . $file . '.rc')) {
            $fileHelper = fopen($directory . $file . '.rc', 'w');
            fwrite($fileHelper, '0');
            fclose($fileHelper);
        }

        $tmpFile = tmpfile();
        $output = NULL;
        // Poslani zdrojoveho kodu obsazeneho v .src souboru do parseru
        exec('cat ' . $directory . $file . '.src | php5.6 ' . $parseScript . ' 2>/dev/null', $output, $returnHelper);

        if ($returnHelper != 0) {
            // Pokud neni navratovy kod parseru 0, porovnava se kod s cislem obsazenym v souboru .rc
            $rcFile = fopen($directory . $file . '.rc', 'r');
            if (fgets($rcFile) == $returnHelper) {
                $tests[$directory][$file] = true;
                $okTests++;
            } else
                $tests[$directory][$file] = false;
            fclose($rcFile);
            $testCount++;
        } else {
            // V opacnem pripade se XML vygenerovane parserem ulozi do docasneho souboru
            // a ten se preda pres parametr interpretu, pricemz se jako pripadny potrebny
            // vstup pro interpret preda ze souboru .in
            file_put_contents(stream_get_meta_data($tmpFile)['uri'], $output);
            $output = NULL;
            exec('python3 ' . $intScript . ' --source=' . stream_get_meta_data($tmpFile)['uri'] . ' < ' . $directory . $file . '.in 2>/dev/null', $output, $returnHelper);

            if ($returnHelper != 0) {
                // V pripade nenuloveho navratoveho kodu se postupuje stejne jako vyse
                $rcFile = fopen($directory . $file . '.rc', 'r');
                if (fgets($rcFile) == $returnHelper) {
                    $tests[$directory][$file] = true;
                    $okTests++;
                } else
                    $tests[$directory][$file] = false;
                fclose($rcFile);
                $testCount++;
            } else {
                // Jinak se porovnava vystup interpretu s vystupem ulozenym v souboru .out
                file_put_contents(stream_get_meta_data($tmpFile)['uri'], $output);
                $output = NULL;
                exec('diff ' . stream_get_meta_data($tmpFile)['uri'] . ' ' . $directory . $file . '.out', $output);

                if (count($output) == 0) {
                    $tests[$directory][$file] = true;
                    $okTests++;
                } else
                    $tests[$directory][$file] = false;
                $testCount++;
            }
        } fclose($tmpFile);
    }
}

// Funkce pro testovani celych slozek, pouziva se pri rekurzivnim prepinaci
function testFolders($directory)
{
    testFiles($directory);
    $folders = explode("\n", shell_exec('ls -1 -d ' . $directory . '*/ 2>/dev/null'));

    // Rekurzivne se zanoruje do jednotlivych slozek a spousti se vsechny testy v techto slozkach obsazenych
    foreach ($folders as $folder) {
        if ($folder != "")
            testFolders($folder);
    }
}

// Vypis napovedy
if (count($options) == 1 && array_key_exists('help', $options)) {
    echo "Skript slouzi pro automaticke testovani postupne aplikace parse.php a interpret.php. " .
        "Projde zadany adresar s testy a vyuzije je pro automaticke otestovani spravne funkcnosti " .
        "obou predchozich programu vcetne vygenerovani prehledneho souhrnu v HTML 5.\n\n" .
        "Parametry:\n" .
        "    --help               vypise na standardni vystup napovedu skriptu\n" .
        "    --directory=path     testy bude hledat v zadanem adresari\n" .
        "    --recursive          testy bude hledat nejen v zadanem adresari, ale i rekurzivne\n" .
        "    --parse-script=file  soubor se skriptem v PHP pro analyzu zdrojoveho kodu v IPPcode18\n" .
        "    --int-script=file    soubor se skriptem v Python pro interpret XML reprezentace kodu\n";
    exit(0);
} elseif (!array_key_exists('help', $options)) {
    $i = 1;
    // Kontrola spravneho formatu argumentu
    if (array_key_exists('directory', $options)) {
        $directory = $options['directory'];
        if (!file_exists($directory))
            $argError = true;
        $i++;
    } if (array_key_exists('parse-script', $options)) {
        $parseScript = $options['parse-script'];
        if (!file_exists($parseScript))
            $argError = true;
        $i++;
    } if (array_key_exists('int-script', $options)) {
        $intScript = $options['int-script'];
        if (!file_exists($intScript))
            $argError = true;
        $i++;
    } if (array_key_exists('recursive', $options)) {
        $recursive = true;
        $i++;
    } if ($i != $argc || $argError)
        exit(10);
}

if (!$recursive)
    testFiles($directory);
else
    testFolders($directory);

// Pripadna zamena korenoveho adresare v poli vysledku testu za nazev
if (key_exists('', $tests)) {
    $tests[basename(dirname(__FILE__))] = $tests[''];
    unset($tests['']);
} ksort($tests);

?>

<!-- HTML pro zobrazeni vysledku testu -->
<!doctype html>
<html lang="cs">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">

    <style>
        html, body, .container {
            min-height: 100%;
        }

        .container {
            display: flex;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }

        table {
            border: 1px solid;
            border-collapse: collapse;
        }

        thead {
            border-bottom: 1px solid;
        }

        .folder-row {
            border-top: 1px solid;
        }

        .folder-row th {
            border-right: 1px solid;
        }

        th, td {
            padding: 5px 16px;
            text-align: center;
        }

        .test-result-ok {
            color: green;
        }

        .test-result-fail {
            color: red;
        }

        .total {
            border-top: 3px solid;
        }

        .total th {
            border-right: 1px solid;
        }

        .total th, .total td {
            padding: 16px 16px;
        }
    </style>

    <title>Výsledky testů</title>
</head>
<body>
<div class="container">
    <h1>Výsledky testů</h1>
    <table class="table">
        <thead>
        <tr>
            <th>Složka</th>
            <th>Test</th>
            <th>Výsledek</th>
        </tr>
        </thead>
        <tbody>
        <!-- Podle toho, jestli byl test uspesny nebo ne, se zbarvi bud zelene, nebo cervene -->
        <?php foreach ($tests as $testFolder => $testResults): ?>
            <tr class="folder-row">
                <th rowspan="<?php echo count($testResults) + 1 ?>"><strong><?php echo $testFolder ?></strong></th>
            </tr>
            <?php foreach ($testResults as $testResult => $result): ?>
            <tr>
                <td><?php echo $testResult ?></td>
                <td class="test-result-<?php echo $result == true ? 'ok' : 'fail' ?>"><strong><?php echo $result == true ? 'OK' : 'FAIL' ?></strong></td>
            </tr>
            <?php endforeach; ?>
        <?php endforeach; ?>
        <tr class="total">
            <th><strong>Celková úspěšnost</strong></th>
            <!-- Vypocitani celkove uspesnosti testu se zaokrouhlenim na dva desetinna mista -->
            <td colspan="2"><?php echo round($okTests / ($testCount / 100), 2) ?>%</td>
        </tr>
        </tbody>
    </table>
</div>
</body>
</html>
