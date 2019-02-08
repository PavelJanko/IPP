<?php

/**
 * Trida, jejiz instance reprezentuji jednotlive tokeny zdrojoveho kodu
 */
class Token
{
    protected $name, $value;

    public function __construct($name, $value = null)
    {
        $this->name = $name;
        $this->value = $value;
    }

    /*
     * Ziskani bud jmena nebo hodnoty tokenu.
     */
    public function get($type = 'n')
    {
        if($type == 'v')
            return htmlspecialchars($this->value);

        return $this->name;
    }

    public function setName($newName)
    {
        $this->name = $newName;
    }
}

class Scanner
{
    protected $source, $string;

    protected $operationCodes = [
        'move', 'createframe', 'pushframe', 'popframe', 'defvar', 'call', 'return',
        'pushs', 'pops',
        'add', 'sub', 'mul', 'idiv', 'lt', 'gt', 'eq', 'and', 'or', 'not', 'int2char', 'stri2int',
        'read', 'write',
        'concat', 'strlen', 'getchar', 'setchar',
        'type',
        'label', 'jump', 'jumpifeq', 'jumpifneq',
        'dprint', 'break'
    ];
    
    protected $newLine = false;
    protected $tokens = [];
    protected $wasEOL = false;
    protected $wasNewLine = false;

    public function __construct($source, $string = '')
    {
        $this->source = $source;
        $this->string = $string;
    }
    
    /*
     * Zjisteni, zda-li se jedna o operacni kod porovnanim
     * s hodnotami preddefinovaneho pole moznych hodnot
     * operanich kodu.
     */
    public function isOperationCode()
    {
        return in_array(strtolower($this->string), $this->operationCodes);
    }

    /**
     * Vytvoreni noveho tokenu a jeho pridani do pole tokenu,
     * ktere je vyuzito pri generovani XML.
     * 
     * @param $name
     * @param null $value
     * @return Token
     */
    public function addToken($name, $value = null)
    {
        $token = new Token($name, $value);
        array_push($this->tokens, $token);
        return $token;
    }

    public function getTokens()
    {
        return $this->tokens;
    }
    
    public function splitStr($needle, $side = 'l', $string = null)
    {
        if($string == null)
            $string = $this->string;
        
        if($side == 'l')
            return substr($string, 0, strpos($string, $needle));
        
        return substr($string, strrpos($string, $needle) + 1, strlen($string));
    }

    /**
     * Hlavni funkce scanneru, ktera vraci nazev (typ) a pripadne i hodnotu
     * nasledujiciho tokenu ve zdrojovem kodu.
     * 
     * @return Token
     */
    public function getNextToken()
    {
        // Osetreni, aby byl vracen maximalne jeden token EOL v rade
        if($this->wasNewLine && !$this->newLine) {
            $this->wasNewLine = false;
            $this->newLine = true;
            return $this->addToken('T_EOL');
        }

        $this->string = '';
        $char = null;
        $instre = 'S_INIT';
        $separator = false;
        $const = false;

        while(true) {
            // Nacteni znaku ze zdroje
            $char = fgetc($this->source);
            if($char == "\r")
                continue;

            // Konecny automat lexikalni analyzy
            switch($instre) {
                // Pocatecni stav
                case 'S_INIT':
                    // Kontrola navesti
                    if($char == '.') {
                        $heading = strtolower(fgets($this->source));

                        if (strpos($heading, PHP_EOL))
                            $this->wasNewLine = true;

                        $heading = trim($heading);

                        if($heading == 'ippcode18' || strpos($heading, "#") && explode("#", $heading, 2)[0] == "ippcode18")
                            return $this->addToken('T_INTRO');
                        else
                            return $this->addToken('T_ERROR');
                    } elseif($char == '#') { // Pokud je zjisten komentar, ignoruje se zbytek radku
                        fgets($this->source);

                        // Osetreni, aby nebyl vracen EOL vicekrat pri viceradkovych komentarich
                        if(!$this->newLine) {
                            $this->newLine = true;
                            return $this->addToken('T_EOL');
                        } break;
                    } elseif($char == PHP_EOL) { // Detekce konce radku, opet osetruji mozne duplicity
                        if(!$this->newLine) {
                            $this->newLine = true;
                            return $this->addToken('T_EOL');
                        } break;
                    } elseif(feof($this->source)) { // Detekce konce vstupu
                        return $this->addToken('T_EOF');
                    } elseif($char != ' ' && $char != "\t") { // Prechod na retezec
                        $this->string .= $char;
                        $instre = 'S_STRING';
                        break;
                    } break; // Nadbytecne mezery jsou ignorovany
                // Stav pro 
                case 'S_STRING':
                    // Podminky pro ukonceni retezce
                    if($char == ' ' || $char == PHP_EOL || $char == "\t" || $char == '#' || feof($this->source)) {
                        if($char == PHP_EOL && !feof($this->source))
                            $this->wasNewLine = true;
                        elseif($char == '#') {
                            fgets($this->source);

                            if(!feof($this->source))
                                $this->wasNewLine = true;
                        }

                        // Pokud se nejedna o prvni token noveho radku, tak se nemuze jednat o operacni kod
                        if(!$this->newLine) {
                            // Pokud hodnota obsahuje oddelovac '@', tak se jedna bud o promennou nebo konstantu
                            if(strpos($this->string, '@')) {
                                $leftPart = explode("@", $this->string, 3)[0];
                                $rightPart = explode("@", $this->string, 3)[1];

                                if (!$const && in_array($leftPart, ['GF', 'LF', 'TF']) &&
                                    $rightPart != "" && !ctype_digit($rightPart[0])) {
                                    return $this->addToken('T_VAR', $this->string);
                                } elseif (in_array($leftPart, ['string', 'int', 'bool'])) {
                                    if($leftPart == 'int' && $rightPart != "") {
                                        if(($rightPart[0] == '-' || $rightPart[0] == '+') && ctype_digit(substr($rightPart, 1))
                                        || ctype_digit(substr($rightPart, 0)))
                                            return $this->addToken('T_CONST', $this->string);
                                        elseif(!ctype_digit($rightPart))
                                            return $this->addToken('T_ERROR');
                                    } elseif($leftPart == "bool" && ($rightPart == "false" || $rightPart == "true"))
                                        return $this->addToken('T_CONST', $this->string);
                                    elseif($leftPart == 'string')
                                        return $this->addToken('T_CONST', $this->string);

                                    return $this->addToken('T_ERROR');
                                }

                                return $this->addToken('T_ERROR');
                            } elseif(!$const && !ctype_digit($this->string[0])) // V opacnem pripade se jedna o navesti
                                return $this->addToken('T_LABEL', $this->string);
                            else
                                return $this->addToken('T_ERROR');
                        } else {
                            $this->newLine = false;

                            if($this->isOperationCode())
                                return $this->addToken('T_OPCODE', strtoupper($this->string));

                            return $this->addToken('T_ERROR');
                        }
                    } elseif($char == "\\") { // Prechod pro specialni escape sekvenci
                        $instre = 'S_ESCAPE';
                    } elseif(!$separator && $char == '@') {
                        $separator = true;
                    } elseif($separator && !ctype_alnum($char) && !in_array($char, ['_', '-', '$', '&', '%', '*']))
                        $const = true;

                    $this->string .= $char;
                    break;
                case 'S_ESCAPE':
                    $this->string .= $char;
                    $subString = $this->splitStr("\\", 'r');

                    if(ctype_digit($subString) && strlen($subString) == 3) {
                        /*
                         * Pokud je escapnuty znak jiny nez ty, ktere mohou byt soucasti promennych ci navesti,
                         * musi se jednat bud o konstantu, nebo dochazi k chybe.
                         */
                        if($const || (!ctype_alnum(chr($subString)) && !in_array(chr($subString), ['_', '-', '$', '&', '%', '*'])))
                            $const = true;

                        $instre = 'S_STRING';
                    } elseif(strlen($subString) == 3)
                        return $this->addToken('T_ERROR');
                    break;
            }
        }
    }
}

class Parser
{
    protected $scanner, $token;

    public function __construct()
    {
        $this->scanner = new Scanner(STDIN);
    }

    /**
     * <operands> -> var <operands>
     * <operands> -> symb <operands>
     * <operands> -> <labelOrType> <operands>
     * <operands> -> EPS
     */
    public function parseOperands()
    {
        if($this->token->get() == 'T_OPCODE' &&
            ($this->token->get('v') == 'CALL' ||
            $this->token->get('v') == 'LABEL' ||
            $this->token->get('v') == 'JUMP' ||
            $this->token->get('v') == 'JUMPIFEQ' ||
            $this->token->get('v') == 'JUMPIFNEQ')) {
            $this->token = $this->scanner->getNextToken();

            if($this->token->get() != 'T_LABEL')
                exit(21);

            $this->parseOperands();
        }

        else {
            $this->token = $this->scanner->getNextToken();

            if ($this->token->get() == 'T_VAR' ||
                $this->token->get() == 'T_CONST')
                $this->parseOperands();
            elseif ($this->token->get() == 'T_LABEL') {
                $this->token->setName('T_TYPE');
                $this->parseOperands();
            } elseif ($this->token->get() != 'T_EOL' &&
                $this->token->get() != 'T_EOF')
                exit(21);
        }
    }

    // <instr> -> <opcode> <operands>
    public function parseInstr()
    {
        $this->token = $this->scanner->getNextToken();

        // Rozdeleni na jednotlive operacni kody se resi az pri generovani XML podle tabulky tokenu
        if($this->token->get() != 'T_OPCODE' && $this->token->get() != 'T_EOF')
            exit(21);
        elseif($this->token->get() != 'T_EOF')
            $this->parseOperands();
    }

    /**
     * <ins-list> -> <instr> EOL <ins-list>
     * <ins-list> -> EPS
     */
    public function parseInsList()
    {
        // Overenim T_EOF resim pravidlo <ins-list> -> EPS
        if($this->token->get() != 'T_EOF') {
            $this->parseInstr();

            if($this->token->get() != 'T_EOL' && $this->token->get() != 'T_EOF')
                exit(21);
            else
                $this->parseInsList();
        }
    }

    // <START> -> .IPPcode18 <ins-list> EOF
    public function parseStart()
    {
        $this->token = $this->scanner->getNextToken();

        // Kontrola pritomnosti navesti
        if($this->token->get() != 'T_INTRO')
            exit(21);
        else {
            $this->token = $this->scanner->getNextToken();
            $this->parseInsList();

            if($this->token->get() == 'T_EOF') {
                // Zakladni konfigurace vystupniho XML a jeho formatu
                $xml = new DOMDocument("1.0", "UTF-8");
		        $xml->formatOutput = true;

		        // Korenovy element s atributem
                $root = $xml->appendChild($xml->createElement('program'));
                $langAttr = $xml->createAttribute('language');
                $langAttr->value = "IPPcode18";
                $root->appendChild($langAttr);

                $argCount = 0;
                $lastInstruction = null;
                $order = 0;

                // Postupuji od zacatku tabulky tokenu ze scanneru
                foreach($this->scanner->getTokens() as $token) {
                    switch($token->get()) {
                        // Jedna se o novou instrukci
                        case 'T_OPCODE':
                            $order++;
                            $argCount = 0;

                            // Ulozeni do pomocne promenne, kterou pouziju u argumentu
                            $lastInstruction = $root->appendChild($xml->createElement('instruction'));

                            // Atribut 'order'
                            $orderAttr = $xml->createAttribute('order');
                            $orderAttr->value = $order;
                            $lastInstruction->appendChild($orderAttr);

                            // Atribut 'opcode'
                            $opcodeAttr = $xml->createAttribute('opcode');
                            $opcodeAttr->value = $token->get('v');
                            $lastInstruction->appendChild($opcodeAttr);
                            break;
                        // Jedna se o argument instrukce
                        case 'T_VAR':
                        case 'T_CONST':
                        case 'T_LABEL':
                        case 'T_TYPE':
                            $argCount++;
                            $argVal = null;

                            // Atribut 'type'
                            $typeAttr = $xml->createAttribute('type');
                            $substring = strtolower(substr($token->get(), strpos($token->get(), '_') + 1, strlen($token->get())));
                            if($substring == 'const') {
                                $typeAttr->value = substr($token->get('v'), 0, strpos($token->get('v'), '@'));
                                $argVal = substr($token->get('v'), strpos($token->get('v'), '@') + 1, strlen($token->get('v')));
                            } else {
                                $typeAttr->value = $substring;
                                $argVal = $token->get('v');
                            }


                            // Pripojeni argumentu k instrukci
                            $argument = $xml->createElement('arg' . $argCount, $argVal);
                            $argument->appendChild($typeAttr);
                            $lastInstruction->appendChild($argument);
                    }
                }

                // Finalni vypis na standartni vystup
                fwrite(STDOUT, $xml->saveXML() . "\n");
                exit(0);
            }
        }
    }
}

if($argc == 2 && $argv[1] == '--help') {
    echo "Skript nacte ze standardniho vstupu zdrojovy kod v IPPcode18, " .
        "zkontroluje lexikalni a syntaktickou spravnost kodu a vypise " .
        "na standardni vystup XML reprezentaci programu dle specifikace.\n\n" .
        "Parametry:\n" .
        "    --help    vypise na standardni vystup napovedu skriptu\n";

    exit(0);
} elseif($argc == 1) {
    $parser = new Parser();
    $parser->parseStart();
} else
    exit(10);
